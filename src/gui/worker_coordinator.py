"""Worker lifecycle coordinator — owns all background worker instances and
their associated progress dialogs.

Extracted from MainWindow so worker lifecycle can be tested and reasoned
about independently of the rest of the window.  The *result handlers*
(``_on_loading_finished``, ``_on_p4k_extract_finished``, etc.) remain in
MainWindow because they update UI state that belongs there; the coordinator
just provides the infrastructure that runs the workers and emits typed
signals when each one finishes.

Signals are used for all cross-thread completions so Qt's queuing mechanism
keeps handler invocations on the main thread.

Usage::

    self.worker_coord = WorkerCoordinator(self)
    # connect to your handlers:
    self.worker_coord.loading_finished.connect(self._on_loading_finished)
    self.worker_coord.loading_error.connect(self._on_loading_error)
    ...
    # start work:
    self.worker_coord.start_file_loading()
    self.worker_coord.start_p4k_extraction()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QMessageBox, QProgressDialog

from src.gui.workers import (
    AnimatedProgressDialog,
    DataForgeExtractWorker,
    EnhancementsGeneratorWorker,
    FileLoaderWorker,
    P4kExtractWorker,
    StartupSyncWorker,
)
from src.utils.settings import AppSettings

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow

logger = logging.getLogger(__name__)

_WORKER_QUIT_TIMEOUT_MS = 5_000  # generous — avoids deadlock


class WorkerCoordinator(QObject):
    """Manages all background worker lifecycle for MainWindow.

    Each public ``start_*`` method creates the worker, wires its internal
    signals to coordinator slots (which clean up + emit coordinator signals),
    and starts it.  Callers connect to the coordinator's signals to receive
    results.
    """

    # ── File loading ──────────────────────────────────────────────────────
    loading_finished = pyqtSignal(list, dict, list)  # entries, defaults, sort_keys
    loading_error = pyqtSignal(str)

    # ── P4K extraction ────────────────────────────────────────────────────
    p4k_finished = pyqtSignal(bool)

    # ── DataForge extraction ──────────────────────────────────────────────
    # operation_running / operation_progress allow MainWindow to wire enhancements_tab
    dataforge_operation_running = pyqtSignal(str)  # label text for tab widget
    dataforge_operation_progress = pyqtSignal(str)  # progress label text
    dataforge_finished = pyqtSignal(bool)

    # ── Enhancements generation ───────────────────────────────────────────
    enhancements_operation_running = pyqtSignal(str)
    enhancements_operation_progress = pyqtSignal(str)
    enhancements_operation_progress_pct = pyqtSignal(int)
    enhancements_finished = pyqtSignal(bool)
    enhancements_error = pyqtSignal(str)

    # ── Startup sync ──────────────────────────────────────────────────────
    startup_source_starting = pyqtSignal(str)
    startup_source_synced = pyqtSignal(str, bool)
    startup_source_error = pyqtSignal(str, str)
    startup_sync_finished = pyqtSignal()

    def __init__(self, parent: QMainWindow) -> None:  # type: ignore[override]
        super().__init__(parent)
        self._parent = parent

        # ── Worker instances ──────────────────────────────────────────────
        self._loader_worker: FileLoaderWorker | None = None
        self._startup_sync_worker: StartupSyncWorker | None = None
        self._p4k_worker: P4kExtractWorker | None = None
        self._enhancements_worker: EnhancementsGeneratorWorker | None = None
        self._forge_worker: DataForgeExtractWorker | None = None

        # ── Progress dialogs ──────────────────────────────────────────────
        self._loading_progress: QProgressDialog | None = None
        self._startup_progress: AnimatedProgressDialog | None = None
        self._p4k_progress: AnimatedProgressDialog | None = None
        self._forge_progress_dialog: AnimatedProgressDialog | None = None
        self._enhancements_progress_dialog: AnimatedProgressDialog | None = None

    # ── Active worker query ───────────────────────────────────────────────

    def has_active_worker(self) -> bool:
        """True while any long-running worker is still executing.

        Used by :meth:`StatusBarManager.update_status` to suppress 'Ready'
        messages that would otherwise clobber in-progress status text.
        """
        workers = (
            self._enhancements_worker,
            self._forge_worker,
            self._p4k_worker,
            self._loader_worker,
            self._startup_sync_worker,
        )
        return any(w is not None and w.isRunning() for w in workers)

    def is_file_loading(self) -> bool:
        """True while a FileLoaderWorker is actively running."""
        return self._loader_worker is not None and self._loader_worker.isRunning()

    def is_startup_sync_running(self) -> bool:
        """True while a StartupSyncWorker is actively running."""
        return self._startup_sync_worker is not None

    # ── File loading ──────────────────────────────────────────────────────

    def start_file_loading(self, message: str = "Loading localization strings...") -> None:
        """Show an animated progress dialog and load files in a background thread.

        Guards against overlapping loads: any previous FileLoaderWorker is
        cleanly shut down before a new one starts.
        """
        if self._loader_worker is not None:
            logger.warning("Previous FileLoaderWorker still exists — cleaning up before starting new load")
            try:
                self._loader_worker.finished.disconnect(self._on_loading_done)
                self._loader_worker.error.disconnect(self._on_loading_err)
            except (TypeError, RuntimeError) as exc:
                if "disconnect" not in str(exc).lower() and not isinstance(exc, TypeError):
                    raise
            if self._loader_worker.isRunning():
                self._loader_worker.quit()
                self._loader_worker.wait(_WORKER_QUIT_TIMEOUT_MS)
            self._loader_worker = None

        if self._loading_progress is not None:
            self._loading_progress.close()
            self._loading_progress = None

        self._loading_progress = AnimatedProgressDialog(message, parent=self._parent, title="Loading")
        self._loader_worker = FileLoaderWorker()
        self._loader_worker.finished.connect(self._on_loading_done)
        self._loader_worker.error.connect(self._on_loading_err)
        self._loader_worker.progress.connect(self._loading_progress.setLabelText)
        self._loader_worker.progress_pct.connect(self._loading_progress.set_progress)
        self._loader_worker.start()

    @pyqtSlot(list, dict, list)
    def _on_loading_done(self, entries: list, default_values: dict, sort_keys: list) -> None:
        if self._loading_progress is not None:
            self._loading_progress.close()
            self._loading_progress = None
        if self._loader_worker is not None:
            self._loader_worker.quit()
            self._loader_worker.wait()
            self._loader_worker = None
        self.loading_finished.emit(entries, default_values, sort_keys)

    @pyqtSlot(str)
    def _on_loading_err(self, message: str) -> None:
        if self._loading_progress is not None:
            self._loading_progress.close()
            self._loading_progress = None
        if self._loader_worker is not None:
            self._loader_worker.quit()
            self._loader_worker.wait()
            self._loader_worker = None
        self.loading_error.emit(message)

    # ── P4K extraction ────────────────────────────────────────────────────

    def start_p4k_extraction(self) -> None:
        """Launch P4kExtractWorker with an animated progress dialog.

        No-ops if a P4K extraction is already running.  Calls
        :meth:`_ensure_tools_downloaded` first; returns silently if the user
        cancels the download.
        """
        if self._p4k_worker is not None:
            return

        if not self._ensure_tools_downloaded():
            return

        p4k_path = AppSettings.get_p4k_path()
        output_path = AppSettings.get_cache_dir() / "base.ini"
        unp4k_exe = AppSettings.get_unp4k_exe_path()

        self._p4k_worker = P4kExtractWorker(p4k_path, output_path, unp4k_exe)
        self._p4k_progress = AnimatedProgressDialog(
            "Extracting global.ini from Data.p4k...", parent=self._parent, title="P4K Extraction"
        )
        self._p4k_worker.progress.connect(self._p4k_progress.setLabelText)
        self._p4k_worker.progress_pct.connect(self._p4k_progress.set_progress)
        self._p4k_worker.error.connect(lambda err: QMessageBox.warning(self._parent, "Extraction Error", err))
        self._p4k_worker.finished.connect(self._on_p4k_done)
        self._p4k_worker.start()
        self._parent.start_spinner()

    @pyqtSlot(bool)
    def _on_p4k_done(self, success: bool) -> None:
        self._parent.stop_spinner()
        if self._p4k_progress is not None:
            self._p4k_progress.close()
            self._p4k_progress = None
        if self._p4k_worker is not None:
            self._p4k_worker.quit()
            self._p4k_worker.wait()
            self._p4k_worker = None
        self.p4k_finished.emit(success)

    # ── DataForge extraction ──────────────────────────────────────────────

    def start_dataforge_extraction(self) -> None:
        """Launch DataForgeExtractWorker in the background.

        No-ops if an extraction is already running.
        """
        if self._forge_worker is not None:
            return

        if not self._ensure_tools_downloaded():
            return

        p4k_path = AppSettings.get_p4k_path()
        unp4k_exe = AppSettings.get_unp4k_exe_path()
        unforge_exe = AppSettings.get_unforge_exe_path()
        forge_dir = AppSettings.get_dataforge_cache_dir()

        label = "Extracting DataForge from Data.p4k…"
        self.dataforge_operation_running.emit(label)
        self._parent.status_bar_mgr.show_message("Extracting DataForge in background — this takes several minutes…")
        self._parent.start_spinner()

        self._forge_progress_dialog = AnimatedProgressDialog(
            "Extracting DataForge from Data.p4k — this takes several minutes…",
            parent=self._parent,
            title="DataForge Extraction",
        )

        self._forge_worker = DataForgeExtractWorker(p4k_path, unp4k_exe, unforge_exe, forge_dir)
        worker = self._forge_worker
        dialog = self._forge_progress_dialog
        worker.progress.connect(self.dataforge_operation_progress)
        worker.progress.connect(self._parent.status_bar_mgr.show_message)
        worker.progress.connect(dialog.setLabelText)
        worker.progress_pct.connect(dialog.set_progress)
        worker.error.connect(self._on_dataforge_err)
        worker.finished.connect(self._on_dataforge_done)
        worker.start()

    @pyqtSlot(str)
    def _on_dataforge_err(self, message: str) -> None:
        logger.error(f"DataForge extraction error: {message}")

    @pyqtSlot(bool)
    def _on_dataforge_done(self, success: bool) -> None:
        self._parent.stop_spinner()
        if self._forge_progress_dialog is not None:
            self._forge_progress_dialog.close()
            self._forge_progress_dialog = None
        if self._forge_worker is not None:
            self._forge_worker.quit()
            self._forge_worker.wait()
            self._forge_worker = None
        self.dataforge_finished.emit(success)

    # ── Enhancements generation ───────────────────────────────────────────

    def start_enhancements_pipeline(self) -> None:
        """Entry point for the enhancements button: extract DataForge if needed, then generate."""
        if self._enhancements_worker is not None or self._forge_worker is not None:
            return

        from src.utils.pak_extractor import dataforge_cache_is_fresh

        forge_dir = AppSettings.get_dataforge_cache_dir()
        p4k_path = AppSettings.get_p4k_path()

        if dataforge_cache_is_fresh(p4k_path, forge_dir):
            self.start_enhancements_generation()
        else:
            self.start_dataforge_extraction()

    def start_enhancements_generation(self, categories: set[str] | None = None) -> None:
        """Launch EnhancementsGeneratorWorker in the background.

        No-ops if a generation is already running.
        """
        if self._enhancements_worker is not None:
            return

        if categories is None:
            categories = AppSettings.get_enabled_enhancement_categories()

        label = "Generating enhancements…"
        self.enhancements_operation_running.emit(label)
        self._parent.status_bar_mgr.show_message("Generating enhancements in background…")

        self._enhancements_progress_dialog = AnimatedProgressDialog(
            "Generating enhanced localizations from DataForge…\n\nThis may take a few minutes on the first run.",
            parent=self._parent,
            title="Generating Enhancements",
        )
        dialog = self._enhancements_progress_dialog

        self._enhancements_worker = EnhancementsGeneratorWorker(categories=categories)
        worker = self._enhancements_worker
        worker.progress.connect(self.enhancements_operation_progress)
        worker.progress.connect(self._parent.status_bar_mgr.show_message)
        worker.progress.connect(dialog.setLabelText)
        worker.progress_pct.connect(dialog.set_progress)
        worker.progress_pct.connect(self.enhancements_operation_progress_pct)
        worker.error.connect(self._on_enhancements_err)
        worker.finished.connect(self._on_enhancements_done)
        worker.start()
        self._parent.start_spinner()

    @pyqtSlot(str)
    def _on_enhancements_err(self, message: str) -> None:
        if self._enhancements_progress_dialog is not None:
            self._enhancements_progress_dialog.close()
            self._enhancements_progress_dialog = None
        self.enhancements_error.emit(message)

    @pyqtSlot(bool)
    def _on_enhancements_done(self, success: bool) -> None:
        self._parent.stop_spinner()
        if self._enhancements_progress_dialog is not None:
            self._enhancements_progress_dialog.close()
            self._enhancements_progress_dialog = None
        if self._enhancements_worker is not None:
            self._enhancements_worker.quit()
            self._enhancements_worker.wait()
            self._enhancements_worker = None
        self.enhancements_finished.emit(success)

    # ── Startup sync ──────────────────────────────────────────────────────

    def start_startup_sync(self) -> None:
        """Start async sync of all enabled remote sources.

        If no remote sources need syncing, emits :attr:`startup_sync_finished`
        immediately so callers can proceed to file loading without a round-trip.
        """
        has_remote_sync = any(
            AppSettings.is_source_enabled(name)
            and AppSettings.get_source_auto_update(name)
            and AppSettings.get_source_path(name).startswith("http")
            for name in AppSettings.AVAILABLE_SOURCES
        )

        if not has_remote_sync:
            self.startup_sync_finished.emit()
            return

        self._parent.status_bar_mgr.show_message("Starting up — syncing sources...")
        self._startup_progress = AnimatedProgressDialog("Syncing sources...", parent=self._parent, title="Starting Up")

        self._startup_sync_worker = StartupSyncWorker()
        self._startup_sync_worker.source_starting.connect(self._on_startup_source_starting)
        self._startup_sync_worker.source_synced.connect(self._on_startup_source_synced)
        self._startup_sync_worker.source_error.connect(self._on_startup_source_error)
        self._startup_sync_worker.finished.connect(self._on_startup_sync_done)
        self._startup_sync_worker.start()

    @pyqtSlot(str)
    def _on_startup_source_starting(self, source_name: str) -> None:
        if self._startup_progress is not None:
            self._startup_progress.setLabelText(f"Syncing {source_name}...")
        self.startup_source_starting.emit(source_name)

    @pyqtSlot(str, bool)
    def _on_startup_source_synced(self, source_name: str, updated: bool) -> None:
        self.startup_source_synced.emit(source_name, updated)

    @pyqtSlot(str, str)
    def _on_startup_source_error(self, source_name: str, message: str) -> None:
        self.startup_source_error.emit(source_name, message)

    @pyqtSlot()
    def _on_startup_sync_done(self) -> None:
        if self._startup_sync_worker is not None:
            self._startup_sync_worker.quit()
            self._startup_sync_worker.wait()
            self._startup_sync_worker = None
        if self._startup_progress is not None:
            self._startup_progress.close()
            self._startup_progress = None
        self.startup_sync_finished.emit()

    # ── Tools download guard ──────────────────────────────────────────────

    def _ensure_tools_downloaded(self) -> bool:
        """Show the tool-download dialog if unp4k/unforge are absent.

        Returns ``True`` when tools are ready to use, ``False`` if the user
        cancelled the download.
        """
        from src.gui.tool_download_dialog import ToolDownloadDialog
        from src.utils.tools_manager import tools_are_present

        if tools_are_present():
            return True
        dlg = ToolDownloadDialog(parent=self._parent)
        return bool(dlg.exec())

    # ── Cleanup ───────────────────────────────────────────────────────────

    def cleanup_all(self) -> None:
        """Gracefully shut down all running workers.

        Called from ``closeEvent`` before the window is destroyed.  Gives
        each worker up to ``_WORKER_QUIT_TIMEOUT_MS`` to stop; logs a warning
        if one doesn't respond in time (avoids hanging the close).
        """
        workers = (
            self._loader_worker,
            self._startup_sync_worker,
            self._p4k_worker,
            self._enhancements_worker,
            self._forge_worker,
        )
        for worker in workers:
            if worker is not None and worker.isRunning():
                if hasattr(worker, "cancel"):
                    worker.cancel()
                worker.quit()
                if not worker.wait(_WORKER_QUIT_TIMEOUT_MS):
                    logger.warning(
                        "Worker %s did not stop within %d ms on close",
                        type(worker).__name__,
                        _WORKER_QUIT_TIMEOUT_MS,
                    )
