"""App-update check lifecycle — owns the AppUpdateCheckerWorker and its result handling.

Extracted from MainWindow so the update-check path can be tested independently
and the worker is managed in one place, following the same pattern as
WorkerCoordinator.

Usage::

    self.update_mgr = UpdateManager(self)
    # No signal wiring needed — UpdateManager shows its own dialogs directly.
    # Trigger a check:
    self.update_mgr.check_for_update(manual=False)   # auto (throttled)
    self.update_mgr.check_for_update(manual=True)    # from UI button
    # On close:
    self.update_mgr.cleanup()
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox

from src.gui.workers import AppUpdateCheckerWorker
from src.utils.settings import AppSettings
from src.utils.version import get_version

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 6 * 60 * 60  # 6 hours between automatic checks
_WORKER_QUIT_TIMEOUT_MS = 5_000


class UpdateManager(QObject):
    """Manages the app-update check worker for MainWindow.

    Auto-checks are throttled to once per :data:`_CHECK_INTERVAL` seconds.
    Manual checks always run and always show feedback regardless of outcome.
    """

    def __init__(self, parent: QMainWindow) -> None:  # type: ignore[override]
        super().__init__(parent)
        self._parent = parent
        self._worker: AppUpdateCheckerWorker | None = None
        self._manual: bool = False

    # ── Public API ────────────────────────────────────────────────────────

    def check_for_update(self, manual: bool = False) -> None:
        """Start an async update check.

        Silently skips if a check is already running.  Auto-checks are
        additionally throttled by :data:`_CHECK_INTERVAL`; manual checks
        always proceed.
        """
        if self._worker is not None and self._worker.isRunning():
            return

        if not manual:
            last = AppSettings.get_last_update_check_epoch()
            if last and (time.time() - last) < _CHECK_INTERVAL:
                return

        self._manual = manual
        self._worker = AppUpdateCheckerWorker()
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

        if manual:
            self._parent.status_bar_mgr.show_message("Checking for updates…")

    def cleanup(self) -> None:
        """Gracefully stop any running worker.  Called from ``closeEvent``."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            if not self._worker.wait(_WORKER_QUIT_TIMEOUT_MS):
                logger.warning("UpdateChecker worker did not stop within %d ms on close", _WORKER_QUIT_TIMEOUT_MS)

    def is_running(self) -> bool:
        """True while an update check is in progress."""
        return self._worker is not None and self._worker.isRunning()

    # ── Internal slots ────────────────────────────────────────────────────

    @pyqtSlot(bool, str, str)
    def _on_finished(self, update_available: bool, new_version: str, release_url: str) -> None:
        manual = self._manual
        self._cleanup_worker()

        if update_available:
            msg_box = QMessageBox(self._parent)
            msg_box.setWindowTitle("Update Available")
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setText(f"<b>Open Strings v{new_version}</b> is available.")
            msg_box.setInformativeText(
                "Click <b>Open Release Page</b> to download the new version,\nor <b>Later</b> to dismiss."
            )
            open_btn = msg_box.addButton("Open Release Page", QMessageBox.ButtonRole.AcceptRole)
            msg_box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()
            if msg_box.clickedButton() is open_btn:
                QDesktopServices.openUrl(QUrl(release_url))
        elif manual:
            QMessageBox.information(
                self._parent, "Up to Date", f"You are running the latest version ({get_version()})."
            )

        if manual:
            self._parent.status_bar_mgr.show_message("Ready")

    @pyqtSlot(str)
    def _on_error(self, message: str) -> None:
        manual = self._manual
        self._cleanup_worker()

        if manual:
            QMessageBox.warning(
                self._parent,
                "Update Check Failed",
                f"Could not reach the update server.\n\nDetail: {message}",
            )
            self._parent.status_bar_mgr.show_message("Ready")

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.quit()
            self._worker.wait()
            self._worker = None
