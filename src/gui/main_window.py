"""Main window for Open Strings."""

import logging
import os
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QModelIndex, Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.gui.config_tab import ConfigTab
from src.gui.enhancements_tab import EnhancementsTab
from src.gui.log_tab import LogTab
from src.gui.string_table_model import (
    COL_CUSTOM,
    COL_STAR,
)
from src.gui.theme import BRAND_FONT_FAMILY, get_button_color, get_button_text_color
from src.gui.workers import (
    AnimatedProgressDialog,
)
from src.merger.ini_merger import merge_sources_by_hierarchy
from src.models.string_model import StringEntry
from src.utils.applied_file_validator import validate_applied_file
from src.utils.entry_filter import filter_entry_indices
from src.utils.locpack_exporter import default_locpack_filename, write_locpack_zip
from src.utils.perf import timed
from src.utils.preview_renderer import _render_preview_html, _stamp_frontend_version
from src.utils.resource import get_resource_path
from src.utils.settings import AppSettings
from src.utils.string_loader import load_source_files, load_sources_from_settings
from src.utils.version import get_version

logger = logging.getLogger(__name__)

# Maximum number of timestamped backup files kept in the backups directory.
# The oldest is pruned when a new backup would exceed this limit.
_MAX_BACKUPS = 5


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Open Strings v{get_version()}")
        self.setGeometry(100, 100, 1400, 800)

        # Set window icon (taskbar + window title bar + favicon)
        icon_path = get_resource_path(os.path.join("assets", "logo.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Data
        self.entries: list[StringEntry] = []
        self.filtered_row_indices: list[int] = []  # noqa: F841  # kept for external compat
        self.default_values: dict[str, str] = {}  # Store default values from cached base source

        # Track whether we've prompted for enhancements on startup (prevents duplicate dialogs)
        # and whether file load should trigger an enhancements freshness check.
        # Both flags now live on startup_flow_mgr; kept as properties for MainWindow callers.

        self.help_dock: QDockWidget | None = None

        # Status-bar manager (owns spinner, channel/version indicators, status text)
        from src.gui.status_bar_manager import StatusBarManager  # noqa: PLC0415

        self.status_bar_mgr = StatusBarManager(self)

        # Update manager — owns AppUpdateCheckerWorker and result dialogs
        from src.gui.update_manager import UpdateManager  # noqa: PLC0415

        self.update_mgr = UpdateManager(self)

        # Worker coordinator — owns all background worker instances and progress dialogs
        from src.gui.worker_coordinator import WorkerCoordinator  # noqa: PLC0415

        self.worker_coord = WorkerCoordinator(self)

        # Build UI
        from src.gui import window_setup as _ws  # noqa: PLC0415

        self._ws = _ws
        self.setup_ui()
        self.restore_window_state()

        # Wire coordinator signals to MainWindow result handlers.
        # Done after setup_ui() so enhancements_tab is available.
        self.worker_coord.loading_finished.connect(self._on_loading_finished)
        self.worker_coord.loading_error.connect(self._on_loading_error)
        self.worker_coord.p4k_finished.connect(self._on_p4k_extract_finished)
        self.worker_coord.dataforge_operation_running.connect(self.enhancements_tab.set_operation_running)
        self.worker_coord.dataforge_operation_progress.connect(self.enhancements_tab.set_operation_progress)
        self.worker_coord.dataforge_finished.connect(self._on_dataforge_extract_finished)
        self.worker_coord.enhancements_operation_running.connect(self.enhancements_tab.set_operation_running)
        self.worker_coord.enhancements_operation_progress.connect(self.enhancements_tab.set_operation_progress)
        self.worker_coord.enhancements_finished.connect(self._on_enhancements_generation_finished)
        self.worker_coord.enhancements_error.connect(self._on_enhancements_generation_error)
        self.worker_coord.startup_source_starting.connect(self._on_startup_source_starting)
        self.worker_coord.startup_source_synced.connect(self._on_startup_source_synced)
        self.worker_coord.startup_source_error.connect(self._on_startup_source_error)
        self.worker_coord.startup_sync_finished.connect(self._on_startup_sync_finished)

        # Tutorial manager — guides first-run; emits tour_finished when done or skipped
        from src.gui.tutorial_manager import TutorialManager  # noqa: PLC0415

        self.tutorial_mgr = TutorialManager(self)
        self.tutorial_mgr.tour_finished.connect(self._start_post_tutorial_tasks)

        # Startup flow manager — P4K/DataForge/enhancements freshness decision tree
        from src.gui.startup_flow_manager import StartupFlowManager  # noqa: PLC0415

        self.startup_flow_mgr = StartupFlowManager(self, self.worker_coord, self.enhancements_tab)

        # Ensure cache directory exists
        AppSettings.get_cache_dir()

        # Startup tasks (source sync + app-update check) are NOT kicked off
        # here on purpose. They get scheduled by _maybe_start_first_run_tutorial
        # so that, on a first-run launch where the guided tour is about to
        # appear, their modal prompts (P4K extraction, "new version available",
        # enhancements pipeline) don't pop over the coach-mark overlay and
        # break the tour. See _start_post_tutorial_tasks.

        # Ensure user.cfg has language setting
        from src.utils.user_cfg import ensure_user_cfg_language

        QTimer.singleShot(0, ensure_user_cfg_language)

        logger.info("MainWindow initialized")

    def _status_bar(self) -> QStatusBar:
        """Delegate to status_bar_mgr."""
        return self.status_bar_mgr._status_bar()

    def setup_ui(self):
        """Build user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Title bar — branded font (Hyperspace Race Expanded Bold)
        self.title_label = QLabel("OPEN STRINGS")
        title_font = QFont(BRAND_FONT_FAMILY)
        title_font.setPointSize(22)
        self.title_label.setFont(title_font)
        main_layout.addWidget(self.title_label)

        self.tagline_label = QLabel("STRING EDITOR FOR STAR CITIZEN")
        main_layout.addWidget(self.tagline_label)
        self._apply_branding_styles()

        # Toolbar on the left; rendered-preview pane on the right.
        toolbar_layout = self._ws.create_toolbar(self)

        self.preview_pane = QTextBrowser()
        self.preview_pane.setReadOnly(True)
        self.preview_pane.setOpenExternalLinks(False)
        self.preview_pane.setPlaceholderText("Select a row to preview its rendered text.")
        self.preview_pane.setMinimumWidth(420)
        # Cap height so the preview pane can't inflate the toolbar row when
        # Config/Enhancements tabs have slack vertical space to give back.
        # setSizePolicy(Preferred, Preferred) prevents QTextBrowser's default
        # Expanding policy from greedily consuming that slack.
        self.preview_pane.setMaximumHeight(120)
        self.preview_pane.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(12)
        toolbar_row.setContentsMargins(0, 0, 12, 0)
        toolbar_row.addLayout(toolbar_layout, stretch=2)
        toolbar_row.addWidget(self.preview_pane, stretch=1)
        main_layout.addLayout(toolbar_row)

        # Tabs
        self.tabs = QTabWidget()
        self._strings_tab_index = self.tabs.addTab(self._ws.create_strings_tab(self), "String Editor")

        # Config tab
        self.config_tab = ConfigTab()
        self.config_tab.merge_requested.connect(self.perform_merge_and_reload)
        self.config_tab.p4k_extract_requested.connect(self._run_p4k_extraction)
        self.config_tab.import_ini_requested.connect(self._handle_import_ini)
        self.config_tab.channel_changed.connect(self._on_channel_changed)
        self.config_tab.data_dir_changed.connect(self._on_data_dir_changed)
        self._config_tab_index = self.tabs.addTab(self.config_tab, "Config")

        # Enhancements tab
        self.enhancements_tab = EnhancementsTab()
        self.enhancements_tab.merge_requested.connect(self.perform_merge_and_reload)
        self.enhancements_tab.enhancements_pipeline_requested.connect(self._run_enhancements_pipeline)
        self._enhancements_tab_index = self.tabs.addTab(self.enhancements_tab, "Enhancements")

        self.log_tab = LogTab()
        self.tabs.addTab(self.log_tab, "Log")

        self.tabs.addTab(self._ws.create_about_tab(self), "About")

        # Revert unapplied enhancement checkbox changes when leaving the tab
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._previous_tab_index = self.tabs.currentIndex()

        main_layout.addWidget(self.tabs)

        # Help side-panel. Created eagerly (before restore_window_state runs)
        # so Qt's native saveState/restoreState can persist its open/closed
        # width across sessions — a dock only gets remembered if it exists
        # with a stable objectName at restoreState() time. Start hidden so
        # first-launch users aren't surprised by a panel they didn't ask for;
        # restoreState will reopen it if the user had it open last session.
        self._ensure_help_dock()
        if self.help_dock is not None:
            self.help_dock.hide()

        # Install the status-bar permanent widgets (spinner, app-version,
        # channel indicator). Order matches the original: spinner first so
        # it lands left-most in the permanent-widget zone.
        self.status_bar_mgr.install_widgets()

    def _on_tab_changed(self, new_index: int):
        """Revert unapplied enhancement checkbox changes when leaving the Enhancements tab."""
        if self._previous_tab_index == self._enhancements_tab_index and new_index != self._enhancements_tab_index:
            self.enhancements_tab.revert_category_checkboxes()
        self._previous_tab_index = new_index

    def create_toolbar(self) -> QVBoxLayout:
        """Delegate to window_setup.create_toolbar."""
        return self._ws.create_toolbar(self)

    def create_strings_tab(self) -> QWidget:
        """Delegate to window_setup.create_strings_tab."""
        return self._ws.create_strings_tab(self)

    def create_about_tab(self) -> QWidget:
        """Delegate to window_setup.create_about_tab."""
        return self._ws.create_about_tab(self)

    def _render_about_html(self):
        """Delegate to window_setup.render_about_html."""
        self._ws.render_about_html(self)

    @pyqtSlot()
    def _set_toolbar_enabled(self, enabled: bool):
        """Toggle toolbar button enabled states."""
        self.apply_btn.setEnabled(enabled)
        self.restore_backup_btn.setEnabled(enabled)
        self.clear_loc_btn.setEnabled(enabled)

    @timed
    def load_default_values(self):
        """Load default values from cached base source in AppData."""
        from src.parser.ini_parser import parse_ini_file

        cache_file = AppSettings.get_cache_dir() / "base.ini"

        if cache_file.exists():
            try:
                # Parse cached base.ini and convert to dict for lookup
                parsed = parse_ini_file(cache_file)
                self.default_values = {key: value for key, value in parsed.items()}
                logger.info(f"Loaded {len(self.default_values)} default values from cache")
            except Exception as e:
                logger.warning(f"Failed to load default values from {cache_file}: {e}")
        else:
            logger.debug(
                f"Cache file not found: {cache_file}. Default values will be empty until sources are downloaded."
            )

    @pyqtSlot()
    @timed
    def apply_to_game(self):
        """Apply merged sources + user edits to game installation and backup existing file."""
        if not self.entries:
            QMessageBox.warning(self, "Warning", "Please load a file first")
            return

        if not AppSettings.get_game_install_path():
            QMessageBox.warning(self, "Warning", "Please configure game install path in Config tab")
            return

        target_path = AppSettings.get_global_ini_path()

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            backup_path = None  # Tracks the backup created this apply (used for restore on validation failure)

            # Backup existing file if it exists
            if target_path.exists():
                backup_dir = AppSettings.get_backups_dir()

                # Find all existing backups
                backup_files = sorted(backup_dir.glob("global.ini.bak_*"), key=lambda f: f.stat().st_mtime)

                # Create new backup first — so we never lose a backup slot if
                # the copy fails (e.g. disk full).
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"global.ini.bak_{timestamp}"
                shutil.copy2(target_path, backup_path)
                logger.info(f"Backed up existing file to {backup_path}")

                # Prune oldest backup now that the new one is confirmed.
                if len(backup_files) >= _MAX_BACKUPS:
                    oldest_backup = backup_files[0]
                    try:
                        oldest_backup.unlink()
                        logger.info(f"Deleted oldest backup: {oldest_backup.name}")
                    except OSError as prune_err:
                        logger.warning(f"Could not delete oldest backup {oldest_backup.name}: {prune_err}")

            # Build final merged dict by re-merging all sources with user edits
            # This ensures Apply uses the latest source versions (catches any file
            # that has changed — or disappeared — since the initial Load).
            sources_dict, hierarchy, _mrk = load_sources_from_settings()

            # Warn if any enabled non-user official source failed to load.
            # Because load_sources_from_settings() runs right above, a source that
            # was present at Load time but is now missing (e.g. network drive gone)
            # will correctly appear here and the user can cancel before a partial
            # apply is written.
            missing_sources = [
                name
                for name in hierarchy
                if name in AppSettings.AVAILABLE_SOURCES
                and name != AppSettings.SOURCE_USER
                and name not in sources_dict
                and AppSettings.is_source_enabled(name)
            ]
            if missing_sources:
                names = ", ".join(missing_sources)
                reply = QMessageBox.warning(
                    self,
                    "Missing Sources",
                    f"The following enabled sources could not be loaded:\n\n  {names}\n\n"
                    "Their customizations will NOT be included in the applied file.\n\n"
                    "Apply anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            # Build user overrides dict from entries with custom_value
            user_overrides_dict = {entry.key: entry.custom_value for entry in self.entries if entry.custom_value}

            # Merge all sources in hierarchy order, with user edits on top
            merged_dict = merge_sources_by_hierarchy(sources_dict, hierarchy, user_overrides_dict)

            # Stamp the main-menu version chip so the game shows that
            # Open Strings is active. Idempotent across re-applies and
            # version bumps; skipped if stock doesn't ship the key.
            merged_dict = _stamp_frontend_version(merged_dict)

            # Get a base file to use for structure preservation
            # Use the first source file from hierarchy
            base_file = None
            for source_name in hierarchy:
                source_path = AppSettings.get_source_path(source_name)
                # Check if it's a URL (remote source) - use cache
                if source_path and (source_path.startswith("http://") or source_path.startswith("https://")):
                    # Map source name to cache file
                    cache_mapping = {
                        AppSettings.SOURCE_GLOBAL: "base.ini",
                    }
                    if source_name in cache_mapping:
                        cache_file = AppSettings.get_cache_dir() / cache_mapping[source_name]
                        if cache_file.exists():
                            base_file = cache_file
                            break
                # Otherwise check if it's a local file that exists
                elif source_path and Path(source_path).exists():
                    base_file = Path(source_path)
                    break

            if not base_file:
                raise FileNotFoundError("No base file found. Configure sources and download them first.")

            # Use merger to preserve original file structure
            from src.merger.ini_merger import merge_ini_files

            merge_ini_files(str(base_file), merged_dict, str(target_path))

            # Validate written file against stock base. Pass the already-parsed
            # base.ini key set so validation skips a redundant 87k-line parse.
            # sources_dict["global"] holds the parsed base.ini from
            # load_sources_from_settings() above; fall back to on-disk read if
            # the global source wasn't loaded (e.g. missing cache).
            stock_keys_hint = set(sources_dict["global"].keys()) if AppSettings.SOURCE_GLOBAL in sources_dict else None
            validation_msg = self._validate_applied_file(target_path, stock_keys=stock_keys_hint)

            if validation_msg:
                # Delete the bad file and restore the backup we just made
                try:
                    target_path.unlink()
                    logger.warning(f"Deleted invalid output file: {target_path}")
                except Exception as del_err:
                    logger.error(f"Could not delete invalid file: {del_err}")

                if backup_path and backup_path.exists():
                    try:
                        shutil.copy2(backup_path, target_path)
                        logger.info(f"Restored backup: {backup_path.name}")
                        restore_note = f"\n\nThe previous file has been restored from backup:\n{backup_path.name}"
                    except Exception as restore_err:
                        logger.error(f"Could not restore backup: {restore_err}")
                        restore_note = "\n\nCould not restore backup — game will use vanilla text."
                else:
                    restore_note = "\n\nNo backup was available to restore."

                self._status_bar().showMessage("Apply failed — validation error")
                QMessageBox.critical(
                    self,
                    "Validation Failed",
                    f"The written file failed validation and has been deleted.\n\n{validation_msg}{restore_note}",
                )
                return

            # Save user overrides to AppData
            from src.utils.user_ini_manager import save_user_ini

            user_count = save_user_ini(self.entries, AppSettings.get_user_ini_path())

            # Count enhancement entries, broken down by category.
            enhancement_categories: Counter[str] = Counter(
                entry.category for entry in self.entries if entry.source_file == "enhancements"
            )
            enhancement_count = sum(enhancement_categories.values())

            # Ensure user.cfg has language setting
            from src.utils.user_cfg import ensure_user_cfg_language

            QTimer.singleShot(0, ensure_user_cfg_language)

            logger.info(f"Applied to game: {target_path}")
            self._status_bar().showMessage(
                f"Applied to game | {user_count} user edits | {enhancement_count} enhancements"
            )
            if enhancement_categories:
                breakdown = "\n".join(f"    {cat}: {count:,}" for cat, count in enhancement_categories.most_common())
                enhancement_block = f"  Open Strings enhancements ({enhancement_count:,} total):\n{breakdown}"
            else:
                enhancement_block = "  Open Strings enhancements: 0"
            QMessageBox.information(
                self,
                "Success",
                f"Applied to {target_path}\n\n  User edits: {user_count}\n{enhancement_block}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply to game: {e}")
            logger.error(f"Error applying to game: {e}")

    def _validate_applied_file(
        self,
        written_path: Path,
        stock_keys: set[str] | None = None,
    ) -> str:
        """Validate the written global.ini. Delegates to applied_file_validator."""
        return validate_applied_file(written_path, AppSettings.get_cache_dir(), stock_keys)

    @pyqtSlot()
    def clear_localization(self):
        """Delete global.ini from the active channel's localization directory, reverting to vanilla text."""
        if not AppSettings.get_game_install_path():
            QMessageBox.warning(self, "Warning", "Please configure game install path in Config tab")
            return

        global_ini = AppSettings.get_global_ini_path()
        loc_dir = global_ini.parent

        if not global_ini.exists():
            QMessageBox.information(
                self,
                "Nothing to Clear",
                "No custom global.ini found in the game's localization directory.\n"
                "The game is already using vanilla text.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Clear Localization",
            f"This will delete the custom global.ini from:\n{loc_dir}\n\n"
            "The game will revert to its default (vanilla) localization text.\n\n"
            "Your overrides are preserved in the app and can be re-applied at any time.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            global_ini.unlink()
            logger.info(f"Deleted {global_ini}")
            self._status_bar().showMessage("Localization cleared — game reverted to vanilla text")
            QMessageBox.information(
                self,
                "Done",
                "Custom localization removed.\n"
                "The game will now use its default text.\n\n"
                "To re-apply your overrides and stat descriptions, click Apply to Game.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete global.ini: {e}")
            logger.error(f"Error clearing localization: {e}")

    @pyqtSlot()
    def clear_cache(self):
        """Delete cached source files from the cache directory. Optionally clear DataForge cache."""
        from PyQt6.QtWidgets import QApplication

        cache_dir = AppSettings.get_cache_dir()
        cached_files = list(cache_dir.glob("*.ini")) + list(cache_dir.glob("*.txt"))

        # Also check for dataforge directory
        dataforge_dir = cache_dir / "dataforge"
        has_dataforge = dataforge_dir.exists()

        if not cached_files and not has_dataforge:
            QMessageBox.information(self, "Cache Empty", "The cache directory is already empty.")
            return

        # First dialog: clear regular cache files
        file_list = "\n".join(f"  {f.name}" for f in sorted(cached_files))
        msg = f"This will delete the following cached files:\n\n{file_list}\n\n"
        msg += "base.ini will need to be re-extracted from Data.p4k before strings can be loaded."

        reply = QMessageBox.question(
            self,
            "Clear Cache",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted, failed = [], []

        # Show progress dialog while deleting files
        progress = AnimatedProgressDialog("Clearing cache files...", parent=self, title="Clearing Cache")

        # Delete cache files
        for f in cached_files:
            try:
                progress.setLabelText(f"Deleting {f.name}...")
                QApplication.processEvents()  # Keep dialog responsive
                f.unlink()
                deleted.append(f.name)
            except Exception as e:
                failed.append(f"{f.name}: {e}")
                logger.error(f"Failed to delete cache file {f}: {e}")

        # Second dialog: ask about DataForge cache (only if it exists)
        clear_dataforge = False
        if has_dataforge:
            progress.close()  # Close progress dialog while asking user
            reply = QMessageBox.question(
                self,
                "Clear DataForge Cache?",
                "Also clear the DataForge entity cache?\n\n"
                "⚠️  Warning: Recreating the DataForge cache takes 5–10 minutes on first run.\n\n"
                "The DataForge cache contains extracted entity data used for generating\n"
                "ship and weapon stats. You can keep this cache and only clear the INI files\n"
                "if you just want to refresh the localization strings.\n\n"
                "Clear DataForge cache?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                clear_dataforge = True
                # Show progress dialog again for DataForge deletion
                progress = AnimatedProgressDialog("Clearing DataForge cache...", parent=self, title="Clearing Cache")

        # Delete dataforge directory if user agreed
        if clear_dataforge:
            try:
                progress.setLabelText("Deleting DataForge directory...")
                QApplication.processEvents()

                # Shared helper — retries with backoff, clears read-only bits,
                # and outlasts OneDrive/Defender/indexer locks that commonly
                # reject the first attempt with WinError 5.
                from src.utils.file_utils import robust_rmtree

                robust_rmtree(dataforge_dir)
                deleted.append("dataforge/")
                logger.info("Deleted DataForge cache directory")
            except Exception as e:
                failed.append(f"dataforge/: {e}")
                logger.error(f"Failed to delete DataForge cache: {e}")

        progress.close()

        self.config_tab._refresh_p4k_status()
        self.entries = []
        self._model.set_data_source([], {}, AppSettings.get_favorite_prefix())

        msg = f"Deleted {len(deleted)} item(s) from cache."
        if failed:
            msg += "\n\nFailed to delete:\n" + "\n".join(failed)
        QMessageBox.information(self, "Cache Cleared", msg)

        # Re-sync all remote sources so they're available for the next Apply.
        # The sync completion will also prompt for p4k extraction if base.ini is missing.
        if not self.worker_coord.is_startup_sync_running():
            self.worker_coord.start_startup_sync()

    @pyqtSlot()
    def export_locpack(self):
        """Package the currently-applied global.ini into a zip for sharing."""
        if not AppSettings.get_game_install_path():
            QMessageBox.warning(self, "Warning", "Please configure game install path in Config tab")
            return

        global_ini = AppSettings.get_global_ini_path()
        if not global_ini.exists():
            QMessageBox.information(
                self,
                "Nothing to Export",
                "No applied global.ini was found in the game's localization directory.\n\n"
                "Click 'Apply to Game' first to write your customizations, then "
                "Export to package them for sharing.",
            )
            return

        channel = AppSettings.get_active_channel()
        default_name = default_locpack_filename(channel)
        downloads_dir = Path.home() / "Downloads"
        default_path = str(downloads_dir / default_name)

        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Export Loc-Pack",
            default_path,
            "Zip files (*.zip)",
        )
        if not dest:
            return

        dest_path = Path(dest)
        try:
            source_size = write_locpack_zip(global_ini, dest_path)
            zip_size = dest_path.stat().st_size
            self._status_bar().showMessage(
                f"Exported loc-pack: {dest_path.name} ({source_size:,} bytes → {zip_size:,} bytes)",
                8000,
            )
        except Exception as exc:
            logger.exception("Export loc-pack failed: %s", exc)
            QMessageBox.critical(self, "Export Failed", f"Could not write zip:\n{exc}")

    @pyqtSlot()
    def open_localization_dir(self):
        """Open the active channel's localization directory in Windows Explorer."""
        if not AppSettings.get_game_install_path():
            QMessageBox.warning(self, "Warning", "Please configure game install path in Config tab")
            return

        loc_dir = AppSettings.get_global_ini_path().parent

        if not loc_dir.exists():
            QMessageBox.warning(
                self,
                "Directory Not Found",
                f"Localization directory not found:\n{loc_dir}\n\nCheck your game install path in the Config tab.",
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(loc_dir)))

    @timed
    def _snapshot_pending_user_edits(self) -> dict:
        """Delegate to pending_edits.snapshot_pending_edits."""
        from src.utils.pending_edits import snapshot_pending_edits  # noqa: PLC0415

        return snapshot_pending_edits(self.entries)

    def _restore_pending_user_edits(self, entries: list, snapshot: dict) -> int:
        """Delegate to pending_edits.restore_pending_edits."""
        from src.utils.pending_edits import restore_pending_edits  # noqa: PLC0415

        return restore_pending_edits(entries, snapshot)

    @pyqtSlot()
    @timed
    def perform_merge_and_reload(self):
        """Perform merge of configured sources and reload table.

        Called when user saves configuration in Config tab. Loads all configured
        sources, merges them in hierarchy order, and updates the table display.
        """
        pending_edits = self._snapshot_pending_user_edits()
        try:
            # Load all configured sources
            sources_dict, hierarchy, enhancements_key_categories = load_sources_from_settings()

            if not sources_dict or not hierarchy:
                QMessageBox.warning(
                    self, "Warning", "No sources configured. Please configure data sources in Config tab."
                )
                return

            self._status_bar().showMessage("Merging sources...")

            try:
                # Load synchronously in main thread
                logger.info("Merging configured sources...")
                entries = load_source_files(
                    sources_dict, hierarchy, enhancements_key_categories=enhancements_key_categories
                )
                logger.info(f"Merge complete: {len(entries)} entries")
                restored = self._restore_pending_user_edits(entries, pending_edits)
                if restored:
                    logger.info(f"Restored {restored} in-memory user edits not yet persisted to user.ini")
                self.entries = entries
                self.default_values = dict(sources_dict.get("global", {}))
                self.update_category_combo()
                self._model.set_data_source(
                    self.entries,
                    self.default_values,
                    AppSettings.get_favorite_prefix(),
                )
                self.apply_filters()

                # Update status bar with entry counts and per-source status
                self._update_status_bar()
            except Exception as e:
                logger.exception(f"Error during merge: {e}")
                QMessageBox.critical(self, "Error", f"Failed to merge sources: {e}")
                self._status_bar().showMessage("Merge failed")

        except Exception as e:
            logger.exception(f"Error in perform_merge_and_reload: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load sources: {e}")

    # ── INI Import ────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _apply_branding_styles(self):
        """Delegate to window_setup.apply_branding_styles."""
        self._ws.apply_branding_styles(self)

    def refresh_action_buttons(self):
        """Re-apply theme-dependent stylesheets on the toolbar action buttons
        and re-render the About tab HTML (whose palette-derived colors are
        baked in at render time). Called after a live theme swap.
        """
        self._apply_branding_styles()
        base = "font-weight: bold; padding: 6px;"
        text = get_button_text_color()
        self.open_loc_dir_btn.setStyleSheet(f"background-color: {get_button_color('open')}; color: {text}; {base}")
        self.apply_btn.setStyleSheet(f"background-color: {get_button_color('apply')}; color: {text}; {base}")
        self.restore_backup_btn.setStyleSheet(f"background-color: {get_button_color('restore')}; color: {text}; {base}")
        self.clear_loc_btn.setStyleSheet(f"background-color: {get_button_color('clear')}; color: {text}; {base}")
        self.clear_cache_btn.setStyleSheet(f"background-color: {get_button_color('clear')}; color: {text}; {base}")
        self.export_locpack_btn.setStyleSheet(f"background-color: {get_button_color('open')}; color: {text}; {base}")
        self.help_btn.setStyleSheet(f"background-color: {get_button_color('open')}; color: {text}; {base}")
        if hasattr(self, "about_browser"):
            self._render_about_html()
        if hasattr(self, "help_browser"):
            self._render_help_html()

    def _handle_import_ini(self):
        """Handle Import INI button: get source, validate, resolve conflicts, merge."""

        from PyQt6.QtWidgets import (
            QDialog,
        )

        from src.parser.ini_parser import parse_ini_file
        from src.utils.updater import download_file
        from src.utils.user_ini_manager import save_user_ini_dict

        # Step 1: Get source path/URL from user
        source = self._get_import_source()
        if not source:
            return

        temp_file = None
        try:
            # Step 2: Resolve to local file
            if source.startswith("https://") or source.startswith("http://"):
                if source.startswith("http://"):
                    QMessageBox.warning(
                        self,
                        "Insecure URL",
                        "Only HTTPS URLs are accepted. The URL you entered uses HTTP and will not be downloaded.",
                    )
                    return
                # Auto-convert GitHub web URLs to raw URLs
                if source.startswith("https://github.com/"):
                    source = source.replace("https://github.com/", "https://raw.githubusercontent.com/")
                    source = source.replace("/blob/", "/")

                self._status_bar().showMessage("Downloading INI file...")
                try:
                    temp_file = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
                    temp_file.close()
                    download_file(source, temp_file.name)
                    resolved_path = temp_file.name
                except Exception as e:
                    QMessageBox.critical(self, "Download Error", f"Failed to download:\n{source}\n\n{e}")
                    return
            else:
                resolved_path = source
                if not Path(resolved_path).exists():
                    QMessageBox.warning(self, "File Not Found", f"File does not exist:\n{resolved_path}")
                    return

            # Step 3: Parse imported file
            imported = parse_ini_file(resolved_path)
            if not imported:
                QMessageBox.warning(self, "Empty File", "The imported file contains no valid key=value entries.")
                return

            # Step 4: Validate against base.ini keys
            if not self.default_values:
                QMessageBox.warning(self, "No Base Data", "Base INI not loaded yet. Extract from Data.p4k first.")
                return

            valid_keys = {k: v for k, v in imported.items() if k in self.default_values}
            excluded_count = len(imported) - len(valid_keys)

            if not valid_keys:
                QMessageBox.warning(
                    self,
                    "No Valid Keys",
                    f"None of the {len(imported)} imported keys exist in base.ini.\nAll keys were excluded.",
                )
                return

            # Step 5: Load current user.ini
            user_ini_path = AppSettings.get_user_ini_path()
            current_user = parse_ini_file(user_ini_path) if user_ini_path.exists() else {}

            # Step 6: Categorize keys
            auto_add = {}
            conflicts = {}
            for key, imported_value in valid_keys.items():
                current_value = current_user.get(key)
                if current_value is None:
                    auto_add[key] = imported_value
                elif current_value != imported_value:
                    conflicts[key] = (current_value, imported_value)
                # else: identical, skip

            # Step 7: Handle cases
            if not auto_add and not conflicts:
                QMessageBox.information(
                    self, "Nothing to Import", "All imported keys already exist in user.ini with the same values."
                )
                return

            if not conflicts:
                reply = QMessageBox.question(
                    self,
                    "Import INI",
                    f"{len(auto_add)} new keys will be added to user.ini.\n"
                    f"{excluded_count} keys excluded (not in base.ini).\n\n"
                    "Proceed?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                resolutions = {}
            else:
                from src.gui.import_dialog import ImportConflictDialog

                dialog = ImportConflictDialog(conflicts, len(auto_add), excluded_count, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                resolutions = dialog.get_resolutions()

            # Step 8: Merge
            final = dict(current_user)
            final.update(auto_add)
            final.update(resolutions)

            # Step 9: Save
            save_user_ini_dict(final, user_ini_path)

            # Step 10: Reload
            self._show_loading_progress("Reloading with imported data...")

            # Step 11: Summary
            QMessageBox.information(
                self,
                "Import Complete",
                f"Import successful.\n\n"
                f"  Added: {len(auto_add)} keys\n"
                f"  Conflicts resolved: {len(resolutions)} keys\n"
                f"  Excluded: {excluded_count} keys",
            )

        except Exception as e:
            logger.exception(f"Import failed: {e}")
            QMessageBox.critical(self, "Import Error", f"Failed to import INI file:\n{e}")
        finally:
            if temp_file:
                try:
                    Path(temp_file.name).unlink(missing_ok=True)
                except Exception:
                    pass

    def _get_import_source(self) -> str | None:
        """Show dialog to get a file path or URL for import."""
        from PyQt6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QVBoxLayout,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Import INI File")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Enter a local file path or URL:"))

        input_row = QHBoxLayout()
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(r"C:\path\to\file.ini or https://example.com/file.ini")
        input_row.addWidget(line_edit)

        browse_btn = QPushButton("Browse...")

        def browse():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select INI File", "", "INI Files (*.ini);;All Files (*)")
            if path:
                line_edit.setText(path)

        browse_btn.clicked.connect(browse)
        input_row.addWidget(browse_btn)
        layout.addLayout(input_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted and line_edit.text().strip():
            return line_edit.text().strip()
        return None

    @pyqtSlot()
    def restore_backup(self):
        """Restore a backup file as the current global.ini."""
        game_path = AppSettings.get_game_install_path()
        if not game_path:
            QMessageBox.warning(self, "Warning", "Please configure game install path in Config tab")
            return

        backup_dir = AppSettings.get_backups_dir()

        # Open file dialog to select backup
        backup_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File to Restore",
            str(backup_dir),
            "Backup Files (*.bak_*);;INI Files (*.ini);;All Files (*)",
        )

        if not backup_file:
            return

        try:
            target_path = AppSettings.get_global_ini_path()
            backup_file_path = Path(backup_file)

            # Restore the backup
            shutil.copy2(str(backup_file_path), str(target_path))

            logger.info(f"Restored backup from {backup_file} to {target_path}")
            QMessageBox.information(self, "Success", f"Backup restored from:\n{backup_file_path.name}")
            self._show_loading_progress("Reloading restored backup...")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore backup: {e}")
            logger.error(f"Error restoring backup: {e}")

    @pyqtSlot()
    def _ensure_help_dock(self) -> QDockWidget:
        """Delegate to window_setup.ensure_help_dock."""
        return self._ws.ensure_help_dock(self)

    def _render_help_html(self):
        """Delegate to window_setup.render_help_html."""
        self._ws.render_help_html(self)

    def _on_help_dock_visibility_changed(self, visible: bool):
        """Keep the toolbar Help button's checked state in sync with the dock."""
        if hasattr(self, "help_btn"):
            # blockSignals so toggling the button here doesn't loop back into
            # show_help and flip the dock visibility again.
            was_blocked = self.help_btn.blockSignals(True)
            try:
                self.help_btn.setChecked(visible)
            finally:
                self.help_btn.blockSignals(was_blocked)

    def show_help(self):
        """Toggle the Help side-panel.

        Help content lives in HELP.md at the project root (bundled into the
        PyInstaller onedir via OpenStrings.spec). The first call creates the
        dock lazily; subsequent calls flip visibility so users can keep the
        guide open as a reference while editing without juggling a modal
        dialog.
        """
        dock = self._ensure_help_dock()
        if dock.isVisible():
            dock.hide()
        else:
            dock.show()
            dock.raise_()

    # ── Guided tour (coach-marks) ─────────────────────────────────────────────

    def _start_tutorial(self) -> None:
        """Delegate to TutorialManager.start_tutorial."""
        self.tutorial_mgr.start_tutorial()

    def _start_post_tutorial_tasks(self) -> None:
        """Fire the deferred startup tasks (source sync + app-update check) once.

        Held back until the guided tour finishes so its modal prompts (P4K
        extraction, app-update dialog, enhancements pipeline) don't pop over
        the coach-mark overlay during first-run. Idempotent — safe to call
        from multiple paths (no-tutorial branch, tour-finished, tour-skipped).
        """
        if getattr(self, "_post_tutorial_tasks_started", False):
            return
        self._post_tutorial_tasks_started = True
        self._start_startup_sync()
        self.update_mgr.check_for_update(manual=False)

    # ── App update check ─────────────────────────────────────────────────────

    def _check_for_app_update(self, manual: bool = False) -> None:
        """Delegate to UpdateManager.check_for_update."""
        self.update_mgr.check_for_update(manual=manual)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.tutorial_mgr.maybe_start_first_run()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if (
            event.key() == Qt.Key.Key_C
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            # Ctrl+Shift+C: Copy filtered rows
            self.copy_filtered_to_clipboard()
        else:
            super().keyPressEvent(event)

    def _has_long_running_worker(self) -> bool:
        """True while an extract/generate/load worker is running. Status-bar
        refreshes that would otherwise fall back to 'Ready' are suppressed
        during that window so in-progress messages aren't clobbered mid-run.
        """
        return self.worker_coord.has_active_worker()

    def _ensure_spinner(self) -> None:
        """Delegate to status_bar_mgr (called from legacy code paths)."""
        self.status_bar_mgr._install_spinner()

    def _ensure_app_version_indicator(self) -> None:
        """Delegate to status_bar_mgr (called from legacy code paths)."""
        self.status_bar_mgr._install_app_version_indicator()

    def _ensure_channel_indicator(self) -> None:
        """Delegate to status_bar_mgr (called from legacy code paths)."""
        self.status_bar_mgr._install_channel_indicator()

    def _tick_spinner(self) -> None:
        """Delegate to status_bar_mgr."""
        self.status_bar_mgr._tick_spinner()

    def start_spinner(self) -> None:
        """Delegate to status_bar_mgr."""
        self.status_bar_mgr.start_spinner()

    def stop_spinner(self) -> None:
        """Delegate to status_bar_mgr."""
        self.status_bar_mgr.stop_spinner()

    def _refresh_channel_indicator(self) -> None:
        """Delegate to status_bar_mgr."""
        self.status_bar_mgr.refresh_channel_indicator()

    def _sync_canonical_source_paths(self, context: str) -> None:
        """Mirror canonical file-backed source paths into QSettings."""
        for source_name, canonical in (
            (AppSettings.SOURCE_GLOBAL, str(AppSettings.get_cache_dir() / "base.ini")),
            (AppSettings.SOURCE_USER, str(AppSettings.get_user_ini_path())),
        ):
            stored = AppSettings.get_source_path(source_name)
            if stored.startswith("http://") or stored.startswith("https://"):
                continue
            if stored != canonical:
                AppSettings.set_source_path(source_name, canonical)
                logger.info(f"Re-synced {source_name} source path {context}: {stored or '(unset)'} → {canonical}")

    @pyqtSlot(str)
    def _on_channel_changed(self, channel: str) -> None:
        """Handle a channel switch from the Config tab.

        Re-runs the merge + reload against the new channel's data: the
        path helpers are already channel-aware, so calling
        :meth:`perform_merge_and_reload` picks up the new cache, user.ini,
        and enhancement INIs automatically. Also refreshes the status-bar
        indicator, the Config tab's P4K status dot, and the Enhancements
        tab's DataForge freshness label so the user sees an immediate
        consistent view across the whole UI.
        """
        logger.info(f"MainWindow reacting to channel change → {channel}")

        # Re-point the stored file-path sources at the new channel's folders.
        # The path helpers themselves (get_cache_dir, get_user_ini_path) are
        # already channel-aware and resolve per-call — but the loader reads
        # the stored path from the registry, so we have to mirror the
        # new values into those entries the same way main() does on startup.
        # Skip any source currently set to a URL to preserve custom remote
        # configs.
        self._sync_canonical_source_paths(f"for channel {channel}")

        self._refresh_channel_indicator()
        self.config_tab._refresh_p4k_status()
        if hasattr(self, "enhancements_tab"):
            # Use the full refresh — it updates the per-category status
            # dots (which file by file reflect whether each enhancement INI
            # exists in this channel's cache) and then calls
            # refresh_forge_status() internally for the DataForge cache
            # label. Calling only refresh_forge_status() would leave the
            # per-category dots showing the prior channel's state.
            self.enhancements_tab.refresh_enhancements_status()

        # Reset the "already prompted once" flag so the category-selection
        # dialog fires again for this channel's (potentially different) set
        # of missing enhancement files. Without this reset,
        # _check_enhancements_freshness silently runs _run_enhancements_pipeline
        # with the prior session's selections — e.g. after switching to a
        # freshly-extracted PTU where all enhancement INIs are missing,
        # the user sees enhancements regenerate with no confirmation.
        # Each channel deserves its own "which enhancements?" prompt.
        self.startup_flow_mgr.reset_startup_state()

        # If the new channel has never been extracted, base.ini won't exist
        # and perform_merge_and_reload() would fail silently with an empty
        # result. Run the same freshness prompt the startup path uses —
        # prompts "Extract from Data.p4k now?" when base.ini is missing or
        # stale. Returns True if extraction was started, in which case the
        # finished handler will trigger the reload itself (don't double-run).
        if self._check_p4k_freshness():
            self._status_bar().showMessage(f"Switched to {channel} — extracting Data.p4k…")
            return

        # base.ini is present and fresh for the new channel. Check whether
        # the channel's DataForge cache is stale relative to its p4k and
        # offer to re-extract if so (background — doesn't block reload).
        self._maybe_prompt_dataforge_refresh()

        self._status_bar().showMessage(f"Switched to {channel} — reloading sources…")
        self.perform_merge_and_reload()

    @pyqtSlot(str)
    def _on_data_dir_changed(self, data_dir: str) -> None:
        """Reload the app against a newly selected Open Strings data folder."""
        logger.info(f"MainWindow reacting to data folder change → {data_dir}")

        AppSettings.ensure_user_ini_file()
        self._sync_canonical_source_paths(f"for data folder {data_dir}")
        self.config_tab._refresh_p4k_status()
        if hasattr(self, "enhancements_tab"):
            self.enhancements_tab.refresh_enhancements_status()

        self.startup_flow_mgr.reset_startup_state()

        if self._check_p4k_freshness():
            self._status_bar().showMessage(f"Data folder changed to {data_dir} — extracting Data.p4k…")
            return

        self._maybe_prompt_dataforge_refresh()
        self._status_bar().showMessage(f"Data folder changed to {data_dir} — reloading sources…")
        self.perform_merge_and_reload()

    def _update_status_bar(self):
        """Delegate to status_bar_mgr."""
        self.status_bar_mgr.update_status(
            entries=self.entries,
            has_running_worker=self._has_long_running_worker(),
        )

    def _set_source_status(self, source_name: str, status: str) -> None:
        """Delegate to status_bar_mgr."""
        self.status_bar_mgr.set_source_status(source_name, status)
        self.status_bar_mgr.update_status(
            entries=self.entries,
            has_running_worker=self._has_long_running_worker(),
        )

    def _start_startup_sync(self):
        """Delegate to WorkerCoordinator.start_startup_sync."""
        self.worker_coord.start_startup_sync()

    @pyqtSlot(str)
    def _on_startup_source_starting(self, source_name: str):
        self._status_bar().showMessage(f"Syncing {source_name}...")

    @pyqtSlot(str, bool)
    def _on_startup_source_synced(self, source_name: str, updated: bool):
        action = "updated" if updated else "up to date"
        logger.info(f"Startup sync: {source_name} {action}")
        label = "updated ↑" if updated else "✓"
        self._set_source_status(source_name, f"{source_name.title()}: {label}")

    @pyqtSlot(str, str)
    def _on_startup_source_error(self, source_name: str, message: str):
        logger.warning(f"Startup sync error ({source_name}): {message}")
        self._set_source_status(source_name, f"{source_name.title()}: ⚠ (offline?)")

    @pyqtSlot()
    def _on_startup_sync_finished(self):
        """Sync complete — delegate to StartupFlowManager."""
        self.startup_flow_mgr.on_startup_sync_finished()

    def _check_p4k_freshness(self) -> bool:
        """Delegate to StartupFlowManager.check_p4k_freshness."""
        return self.startup_flow_mgr.check_p4k_freshness()

    def _maybe_prompt_dataforge_refresh(self) -> None:
        """Delegate to StartupFlowManager.maybe_prompt_dataforge_refresh."""
        self.startup_flow_mgr.maybe_prompt_dataforge_refresh()

    def _check_enhancements_freshness(self):
        """Delegate to StartupFlowManager.check_enhancements_freshness."""
        self.startup_flow_mgr.check_enhancements_freshness()

    def _show_enhancement_category_dialog(self, missing_keys: list[str]) -> set[str] | None:
        """Delegate to StartupFlowManager._show_enhancement_category_dialog."""
        return self.startup_flow_mgr._show_enhancement_category_dialog(missing_keys)

    def _show_loading_progress(self, message: str = "Loading localization strings...") -> None:
        """Delegate to WorkerCoordinator.start_file_loading."""
        self.worker_coord.start_file_loading(message)

    @pyqtSlot(list, dict, list)
    @timed
    def _on_loading_finished(self, entries: list, default_values: dict, sort_keys: list):
        """Handle file loading completion.

        Args:
            entries: Merged StringEntry list.
            default_values: Global source key→value dict (for the Default Value column).
            sort_keys: Pre-computed grouped sort keys (one per entry).
        """
        # Preserve in-memory edits the user hasn't Applied yet — Generate
        # Enhancements (and other reload paths) hit this slot with freshly
        # loaded entries whose custom_value comes only from user.ini, so
        # any un-saved edits would be silently dropped without this.
        pending_edits = self._snapshot_pending_user_edits()
        restored = self._restore_pending_user_edits(entries, pending_edits)
        if restored:
            logger.info(f"Restored {restored} in-memory user edits not yet persisted to user.ini")

        self.default_values = default_values
        self.entries = entries
        self.update_category_combo()

        # Push data into the model — the view renders only visible rows, so this is instant
        self._model.set_data_source(
            self.entries,
            self.default_values,
            AppSettings.get_favorite_prefix(),
            sort_keys=sort_keys,
        )
        self.apply_filters()

        # Update status bar with entry counts and per-source status
        self._update_status_bar()

        # If enhancements check was deferred during startup, do it now (after file loading completes)
        # This avoids concurrent I/O contention between file loader and enhancements generator
        if self.startup_flow_mgr.check_enhancements_after_loading:
            self.startup_flow_mgr.check_enhancements_after_loading = False
            self.startup_flow_mgr.check_enhancements_freshness()

    @pyqtSlot(str)
    def _on_loading_error(self, error_msg: str):
        """Handle file loading error."""
        if "No sources configured" in error_msg or "file not found" in error_msg.lower():
            self._status_bar().showMessage(
                'Base localization file not found — use "Extract from Data.p4k" in the Config tab to get started.'
            )
            self.tabs.setCurrentIndex(self._config_tab_index)
            return
        QMessageBox.critical(self, "Error", f"Failed to load sources: {error_msg}")

    def _run_enhancements_pipeline(self):
        """Delegate to WorkerCoordinator.start_enhancements_pipeline."""
        self.worker_coord.start_enhancements_pipeline()

    def _run_enhancements_generation(self, categories: set[str] | None = None):
        """Delegate to WorkerCoordinator.start_enhancements_generation."""
        self.worker_coord.start_enhancements_generation(categories)

    def _on_enhancements_generation_error(self, message: str):
        logger.error(f"Enhancements generation error: {message}")

    def _on_enhancements_generation_finished(self, success: bool):
        self.enhancements_tab.set_operation_idle()
        self.enhancements_tab.refresh_enhancements_status()

        status_bar = self._status_bar()
        if success:
            status_bar.showMessage("Enhancements generated — reloading entries…")
            self.worker_coord.start_file_loading("Reloading strings with updated enhancements…")
        else:
            status_bar.showMessage("Enhancement generation failed — check the Log tab for details")

    def _run_dataforge_extraction(self):
        """Delegate to WorkerCoordinator.start_dataforge_extraction."""
        self.worker_coord.start_dataforge_extraction()

    def _on_dataforge_extract_finished(self, success: bool):
        self.enhancements_tab.refresh_forge_status()

        status_bar = self._status_bar()
        if success:
            status_bar.showMessage("DataForge extracted — generating enhancements…")
            self.worker_coord.start_enhancements_generation()
        else:
            self.enhancements_tab.set_operation_idle()
            status_bar.showMessage("DataForge extraction failed — check the Log tab for details")

    def _run_p4k_extraction(self):
        """Delegate to WorkerCoordinator.start_p4k_extraction."""
        self.worker_coord.start_p4k_extraction()

    def _on_p4k_extract_finished(self, success: bool):
        """Handle P4K extraction completion."""
        if success:
            local_path = str(AppSettings.get_cache_dir() / "base.ini")
            AppSettings.set_source_path(AppSettings.SOURCE_GLOBAL, local_path)
            AppSettings.set_source_auto_update(AppSettings.SOURCE_GLOBAL, False)
            self.config_tab._refresh_p4k_status()
            self.startup_flow_mgr.check_enhancements_after_loading = True
            self.worker_coord.start_file_loading("Reloading with extracted base.ini...")

    def closeEvent(self, event):
        """Save state and overrides before closing."""
        # Auto-save overrides if there are unsaved edits
        if self.entries and not self.worker_coord.is_file_loading():
            try:
                from src.utils.user_ini_manager import save_user_ini, should_autosave_user_ini

                user_ini_path = AppSettings.get_user_ini_path()
                if should_autosave_user_ini(self.entries, user_ini_path):
                    save_user_ini(self.entries, user_ini_path)
            except Exception as e:
                logger.error(f"Failed to auto-save overrides on exit: {e}")

        # Detach log handler before widgets are destroyed
        self.log_tab.remove_handler()

        # Cleanly shut down all background workers before the window is destroyed.
        # Without this, Qt may tear down the window mid-operation and leave threads
        # in an undefined state or DataForge temp files half-written.
        self.worker_coord.cleanup_all()
        self.update_mgr.cleanup()

        # Flush registry writes
        AppSettings.settings().sync()

        # Stop the status-bar spinner timer
        self.status_bar_mgr.cleanup()

        # Save window state
        AppSettings.set_window_geometry(self.saveGeometry().data())
        AppSettings.set_window_state(self.saveState().data())

        event.accept()

    @timed
    def _filtered_entry_indices(self) -> list[int]:
        """Return indices into self.entries for entries passing the current filters."""
        return filter_entry_indices(
            entries=self.entries,
            default_values=self.default_values,
            column_filters=self.filter_header.get_filter_texts(),
            category_filter=self.category_combo.currentText(),
            status_filter=self.status_combo.currentText(),
            hide_unmodified=self.hide_unmodified_check.isChecked(),
            favorites_only=self.favorites_only_check.isChecked(),
            favorite_prefix=AppSettings.get_favorite_prefix(),
        )

    @timed
    def update_category_combo(self):
        """Update category combo with unique categories from entries.

        Always includes standard categories (Ships, Ship Items, Missions, Other)
        plus any custom categories found in the entries.
        """
        # Get unique categories from entries
        entry_categories = set(e.category for e in self.entries)

        # Always include standard categories, even if no entries exist for them yet
        standard_categories = {"Ships", "Ship Items", "Missions", "Commodities", "Other"}
        categories = sorted(standard_categories | entry_categories)

        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("All")
        self.category_combo.addItems(categories)
        self.category_combo.blockSignals(False)

    def _entry_index_for_row(self, row: int) -> int:
        """Map a visual table row to an index into self.entries."""
        return self._model.entry_index_for_row(row)

    def _on_preview_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Refresh the preview pane when the selected row changes."""
        if not current.isValid() or not self.entries:
            self.preview_pane.clear()
            return
        try:
            entry = self.entries[self._entry_index_for_row(current.row())]
        except (IndexError, AttributeError):
            self.preview_pane.clear()
            return
        raw = entry.custom_value or entry.original_value or ""
        self.preview_pane.setHtml(_render_preview_html(entry.key, raw))

    @pyqtSlot()
    def apply_filters(self):
        """Apply filters by updating the model's filtered index list."""
        if not self.entries:
            return
        indices = self._filtered_entry_indices()
        self._model.set_filtered_indices(indices)
        self.table_status_label.setText(f"Showing {len(indices)} of {len(self.entries)} strings")

    @pyqtSlot()
    def _on_grouped_sort(self):
        """Apply grouped sort by Key column."""
        self._model.set_grouped_sort(True)
        self._model.sort(1, Qt.SortOrder.AscendingOrder)

    @pyqtSlot()
    def clear_filters(self):
        """Clear all filters."""
        self.category_combo.blockSignals(True)
        self.status_combo.blockSignals(True)
        self.hide_unmodified_check.blockSignals(True)
        self.favorites_only_check.blockSignals(True)

        self.filter_header.clear_all()
        self.category_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.hide_unmodified_check.setChecked(False)
        self.favorites_only_check.setChecked(False)

        self.category_combo.blockSignals(False)
        self.status_combo.blockSignals(False)
        self.hide_unmodified_check.blockSignals(False)
        self.favorites_only_check.blockSignals(False)

        self.apply_filters()

    @pyqtSlot()
    def copy_filtered_to_clipboard(self):
        """Copy all visible filtered rows to clipboard (tab-separated)."""
        lines = []
        lines.append("Key\tOriginal Value\tCurrent Value\tCustom Value\tStatus")

        for proxy_row in range(self._model.rowCount()):
            entry_idx = self._entry_index_for_row(proxy_row)
            if entry_idx >= len(self.entries):
                continue

            entry = self.entries[entry_idx]
            original = self.default_values.get(entry.key, entry.original_value)
            line = f"{entry.key}\t{original}\t{entry.original_value}\t{entry.custom_value}\t{entry.status}"
            lines.append(line)

        if len(lines) <= 1:
            QMessageBox.information(self, "Copy Filtered", "No rows to copy.")
            return

        text_to_copy = "\n".join(lines)
        clipboard = QApplication.clipboard()
        if clipboard is None:
            QMessageBox.warning(self, "Copy Error", "Clipboard is not available.")
            return
        clipboard.setText(text_to_copy)
        QMessageBox.information(self, "Copy Filtered", f"Copied {len(lines) - 1} rows to clipboard.")

    def show_context_menu(self, position):
        """Show right-click context menu."""
        proxy_index = self.table.indexAt(position)
        if not proxy_index.isValid():
            return

        proxy_row = proxy_index.row()
        entry_idx = self._entry_index_for_row(proxy_row)
        if entry_idx >= len(self.entries):
            return

        entry = self.entries[entry_idx]
        prefix = AppSettings.get_favorite_prefix()
        is_favorite = entry.custom_value.startswith(prefix)

        menu = QMenu(self)
        menu.addAction("Copy Cell", lambda: self.copy_cell(proxy_index))
        menu.addAction("Copy Key", lambda: self.copy_key(proxy_row))
        menu.addSeparator()
        menu.addAction("Edit", lambda: self.edit_cell(proxy_row))
        menu.addAction("Reset to Original", lambda: self.reset_to_original(proxy_row))
        menu.addSeparator()
        menu.addAction("Copy All Filtered", lambda: self.copy_filtered_to_clipboard())

        if entry.category == "Ships":
            menu.addSeparator()
            if is_favorite:
                menu.addAction("★ Remove from Favorites", lambda: self.toggle_favorite(proxy_row))
            else:
                menu.addAction("★ Add to Favorites", lambda: self.toggle_favorite(proxy_row))

        menu.exec(self.table.mapToGlobal(position))

    def edit_cell(self, proxy_row: int):
        """Edit custom value cell."""
        self.table.edit(self._model.index(proxy_row, COL_CUSTOM))

    def reset_to_original(self, proxy_row: int):
        """Reset custom value to original."""
        entry_idx = self._entry_index_for_row(proxy_row)
        if entry_idx < len(self.entries):
            entry = self.entries[entry_idx]
            entry.custom_value = ""
            entry.status = "Unmodified"
            self._model.notify_entry_changed(entry_idx)

    def copy_cell(self, proxy_index: QModelIndex):
        """Copy the clicked cell's text to clipboard."""
        text = proxy_index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(str(text))

    def copy_key(self, proxy_row: int):
        """Copy key to clipboard."""
        entry_idx = self._entry_index_for_row(proxy_row)
        if entry_idx < len(self.entries):
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self.entries[entry_idx].key)
                self._status_bar().showMessage(f"Copied: {self.entries[entry_idx].key}")

    @pyqtSlot(QModelIndex)
    def _on_cell_clicked(self, proxy_index: QModelIndex):
        """Handle cell clicks — col 4 (★) toggles favorite for Ship rows."""
        if proxy_index.column() == COL_STAR:
            entry_idx = self._entry_index_for_row(proxy_index.row())
            if entry_idx < len(self.entries) and self.entries[entry_idx].category == "Ships":
                self.toggle_favorite(proxy_index.row())

    def toggle_favorite(self, proxy_row: int):
        """Add or remove the sort prefix from a ship's custom value."""
        entry_idx = self._entry_index_for_row(proxy_row)
        if entry_idx >= len(self.entries):
            return

        entry = self.entries[entry_idx]
        prefix = AppSettings.get_favorite_prefix()

        if entry.custom_value.startswith(prefix):
            new_value = entry.custom_value[len(prefix) :]
            entry.custom_value = new_value if new_value != entry.original_value else ""
        else:
            base = entry.custom_value if entry.custom_value else entry.original_value
            entry.custom_value = prefix + base

        entry.status = "Modified" if entry.custom_value else "Unmodified"

        # Notify the model — view updates automatically
        self._model.notify_entry_changed(entry_idx)

    def restore_window_state(self):
        """Restore window geometry and state."""
        geometry = AppSettings.get_window_geometry()
        state = AppSettings.get_window_state()

        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)

    def create_anchor_id(self, text: str) -> str:
        """Convert text to anchor ID."""
        from src.gui.markdown_renderer import create_anchor_id

        return create_anchor_id(text)

    def markdown_to_html(self, markdown_text: str) -> str:
        """Convert markdown to HTML with theme-aware styling."""
        from PyQt6.QtGui import QPalette
        from PyQt6.QtWidgets import QApplication

        from src.gui.markdown_renderer import markdown_to_html as _render

        palette = QApplication.palette()
        return _render(
            markdown_text,
            text_color=palette.color(QPalette.ColorRole.Text).name(),
            base_color=palette.color(QPalette.ColorRole.Base).name(),
            link_color=palette.color(QPalette.ColorRole.Link).name(),
        )

    def _convert_markdown_links(self, text: str) -> str:
        """Delegate to markdown_renderer module."""
        from src.gui.markdown_renderer import _convert_markdown_links

        return _convert_markdown_links(text)

    def _convert_markdown_inline(self, text: str) -> str:
        """Delegate to markdown_renderer module."""
        from src.gui.markdown_renderer import _convert_markdown_inline

        return _convert_markdown_inline(text)
