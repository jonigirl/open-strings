"""Startup flow orchestration: P4K freshness, DataForge staleness, enhancements freshness.

Extracted from MainWindow so the ~220-line startup decision tree can be tested
without triggering Qt widget construction.
"""

import logging

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.utils.settings import AppSettings

logger = logging.getLogger(__name__)


class StartupFlowManager(QObject):
    """Orchestrates the startup freshness-check decision tree.

    Also called from channel-change and data-dir-change handlers, since those
    run the same P4K / DataForge freshness prompts.

    State:
        enhancements_prompted: Set to True after the category-selection dialog
            is shown on startup.  Reset to False when the channel or data
            directory changes so the dialog fires again for the new context.
        check_enhancements_after_loading: Set to True when the startup or P4K
            extraction path wants ``_on_loading_finished`` to trigger a
            subsequent enhancements freshness check. MainWindow reads this flag
            after each load completes.
    """

    def __init__(
        self,
        parent: QWidget,
        worker_coord,
        enhancements_tab,
    ) -> None:
        super().__init__(parent)
        self._parent = parent
        self._worker_coord = worker_coord
        self._enhancements_tab = enhancements_tab

        self.enhancements_prompted: bool = False
        self.check_enhancements_after_loading: bool = False

    def reset_startup_state(self) -> None:
        """Reset per-session flags — call when channel or data directory changes."""
        self.enhancements_prompted = False

    def on_startup_sync_finished(self) -> None:
        """Startup-sync complete — check P4K freshness, then load sources."""
        p4k_extraction_started = self.check_p4k_freshness()
        if p4k_extraction_started:
            return

        self.maybe_prompt_dataforge_refresh()

        self.check_enhancements_after_loading = True
        self._worker_coord.start_file_loading()

    def check_p4k_freshness(self) -> bool:
        """Prompt to extract from Data.p4k if base.ini is missing or outdated.

        Returns:
            True if P4K extraction was started (caller should defer file loading).
            False if no extraction is needed or user declined.
        """
        p4k_path = AppSettings.get_p4k_path()
        base_ini = AppSettings.get_cache_dir() / "base.ini"

        if not p4k_path.exists():
            return False  # silently skip — game path not set

        base_missing = not base_ini.exists()
        p4k_newer = (not base_missing) and (p4k_path.stat().st_mtime > base_ini.stat().st_mtime)

        if not base_missing and not p4k_newer:
            return False  # cache is present and up to date

        if base_missing:
            msg = (
                "No base localization file found in cache.\n\n"
                "Extract global.ini from Data.p4k now?\n"
                "(Required to load and display localization strings.)"
            )
        else:
            msg = (
                "Data.p4k is newer than your cached base.ini.\n\n"
                "Extract global.ini from Data.p4k now?\n"
                "(This gives you stock strings matching your exact installed game version.)"
            )

        reply = QMessageBox.question(
            self._parent,
            "Extract from Data.p4k",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._worker_coord.start_p4k_extraction()
            return True
        return False

    def maybe_prompt_dataforge_refresh(self) -> None:
        """Prompt to re-extract DataForge if its cache is stale vs. Data.p4k.

        Called during startup after base.ini passes its freshness check.
        A stale DataForge cache doesn't block the base-string workflow — the
        table loads fine — but it means the next enhancements regeneration
        will run against old entity data, so stats/missions/blueprints will
        drift from what the current game build actually ships. Users who
        notice the passive ``DataForge: cache outdated`` label on the
        Enhancements tab want to act on it; surfacing a Yes/No dialog on
        startup consolidates the prompt into the same flow as the base.ini
        prompt above.

        Silent no-op when the cache is fresh, when unp4k or Data.p4k is
        missing (no signal to act on), when any worker is already running
        (don't stack prompts), or when the cache has no stamp file yet (that's
        the "never extracted" case — the existing ``check_enhancements_freshness``
        prompt handles it via a category-selection dialog after the first load).

        Does NOT defer file loading — unlike the base.ini case, loading
        the table doesn't depend on DataForge. The extract runs in the
        background and chains into enhancements generation on completion.
        """
        from src.utils.pak_extractor import dataforge_cache_is_fresh

        if self._worker_coord.has_active_worker():
            return
        p4k_path = AppSettings.get_p4k_path()
        if not p4k_path.exists():
            return
        forge_dir = AppSettings.get_dataforge_cache_dir()
        if not (forge_dir / ".p4k_mtime").exists():
            # Never extracted — handled later by check_enhancements_freshness,
            # which shows a richer category-selection dialog.
            return
        if dataforge_cache_is_fresh(p4k_path, forge_dir):
            return

        reply = QMessageBox.question(
            self._parent,
            "DataForge Cache Outdated",
            "Your DataForge entity cache is older than the current Data.p4k.\n\n"
            "Re-extract DataForge and regenerate enhancements now?\n\n"
            "This takes 5–10 minutes and runs in the background — you can keep "
            "editing strings while it works. Skip for now if you'd rather not wait; "
            "you can always trigger this from the Enhancements tab.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._worker_coord.start_dataforge_extraction()

    def check_enhancements_freshness(self) -> None:
        """If enabled enhancement files are missing, prompt to generate them.

        Shows a category selection dialog on startup. If called again after P4K
        extraction and we already prompted, runs generation with saved selections.
        """
        cache_dir = AppSettings.get_cache_dir()
        if not (cache_dir / "base.ini").exists():
            return
        if self._worker_coord.has_active_worker():
            return

        enabled = AppSettings.get_enabled_enhancement_categories()
        missing = [key for key in enabled if not (cache_dir / AppSettings.ENHANCEMENTS_FILES[key]).exists()]
        if not missing:
            return

        p4k_path = AppSettings.get_p4k_path()
        if not p4k_path.exists():
            return

        if self.enhancements_prompted:
            self._worker_coord.start_enhancements_pipeline()
            return

        self.enhancements_prompted = True
        selected = self._show_enhancement_category_dialog(missing)
        if selected:
            self._worker_coord.start_enhancements_pipeline()

    def _show_enhancement_category_dialog(self, missing_keys: list[str]) -> set[str] | None:
        """Show a dialog letting the user select which enhancement categories to generate.

        Args:
            missing_keys: List of category keys that are currently missing.

        Returns:
            Set of selected category keys, or None if user clicked Skip.
        """
        missing_file_keys = set(missing_keys)
        missing_checkbox_keys = set()
        for checkbox_key, file_keys in AppSettings.ENHANCEMENT_CATEGORY_FILES.items():
            if any(fk in missing_file_keys for fk in file_keys):
                missing_checkbox_keys.add(checkbox_key)

        dialog = QDialog(self._parent)
        dialog.setWindowTitle("Generate Enhancements")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)

        n = len(missing_checkbox_keys)
        noun = "category is" if n == 1 else "categories are"
        layout.addWidget(
            QLabel(
                f"{n} enhancement {noun} missing.\n"
                "Select which to generate.\n"
                "You can change this later in the Enhancements tab."
            )
        )

        layout.addSpacing(8)

        checkboxes: dict[str, QCheckBox] = {}
        for key, label in AppSettings.ENHANCEMENT_LABELS.items():
            cb = QCheckBox(label)
            if key in missing_checkbox_keys:
                cb.setChecked(True)
                cb.setText(f"{label}  (missing)")
            else:
                cb.setChecked(False)
            checkboxes[key] = cb
            layout.addWidget(cb)

        layout.addSpacing(8)

        info = QLabel(
            "DataForge data will be extracted automatically if not already cached.\nFirst run takes ~5-10 minutes."
        )
        info.setProperty("role", "secondary")
        info.setStyleSheet("font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addSpacing(8)

        button_row = QHBoxLayout()
        generate_btn = QPushButton("Generate")
        generate_btn.setDefault(True)
        skip_btn = QPushButton("Skip")

        generate_btn.clicked.connect(dialog.accept)
        skip_btn.clicked.connect(dialog.reject)

        button_row.addStretch()
        button_row.addWidget(skip_btn)
        button_row.addWidget(generate_btn)
        layout.addLayout(button_row)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            for key, cb in checkboxes.items():
                if key in missing_checkbox_keys:
                    AppSettings.set_enhancement_category_enabled(key, cb.isChecked())
            self._enhancements_tab.revert_category_checkboxes()
            self._enhancements_tab.refresh_enhancements_status()
            return AppSettings.get_enabled_enhancement_categories()

        return None
