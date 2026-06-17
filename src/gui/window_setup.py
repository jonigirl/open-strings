"""UI-building helpers extracted from MainWindow.

Each function accepts *parent* (the MainWindow instance) and sets widget
attributes directly on it so the window can reference them by name as usual.
Using TYPE_CHECKING for the type hint avoids the circular import that would
arise if this module imported MainWindow at runtime.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.gui.filter_header import FilterHeaderView
from src.gui.string_table_model import COL_CUSTOM, StringTableModel
from src.gui.theme import (
    get_button_color,
    get_button_text_color,
    get_tagline_color,
    get_title_color,
)
from src.gui.workers import SelectAllDelegate
from src.utils.resource import get_resource_path
from src.utils.version import get_version

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def create_toolbar(parent: MainWindow) -> QVBoxLayout:
    """Create the toolbar layout with buttons and filter row.

    Sets the following attributes on *parent*: ``open_loc_dir_btn``,
    ``apply_btn``, ``restore_backup_btn``, ``clear_loc_btn``,
    ``clear_cache_btn``, ``export_locpack_btn``, ``help_btn``,
    ``tutorial_btn``, ``category_combo``, ``status_combo``,
    ``hide_unmodified_check``, ``favorites_only_check``,
    ``grouped_sort_btn``, ``clear_filters_btn``, ``copy_filtered_btn``.
    """
    layout = QVBoxLayout()

    # ── Button row ────────────────────────────────────────────────────────
    button_layout = QHBoxLayout()

    parent.open_loc_dir_btn = QPushButton("Open Localization Dir")
    parent.open_loc_dir_btn.setStyleSheet(
        f"background-color: {get_button_color('open')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.open_loc_dir_btn.setToolTip("Open the game's localization directory in Windows Explorer")
    parent.open_loc_dir_btn.clicked.connect(parent.open_localization_dir)
    button_layout.addWidget(parent.open_loc_dir_btn)

    parent.apply_btn = QPushButton("Apply to Game")
    parent.apply_btn.setStyleSheet(
        f"background-color: {get_button_color('apply')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.apply_btn.setToolTip(
        "Write the merged table contents to the game's global.ini. "
        "A timestamped backup of the current global.ini is created first."
    )
    parent.apply_btn.clicked.connect(parent.apply_to_game)
    button_layout.addWidget(parent.apply_btn)

    parent.restore_backup_btn = QPushButton("Restore Backup")
    parent.restore_backup_btn.setStyleSheet(
        f"background-color: {get_button_color('restore')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.restore_backup_btn.setToolTip(
        "Restore a previous global.ini from Documents\\Open Strings\\backups\\. "
        "Up to 5 timestamped backups are kept; the oldest is pruned when a new one is created."
    )
    parent.restore_backup_btn.clicked.connect(parent.restore_backup)
    button_layout.addWidget(parent.restore_backup_btn)

    parent.clear_loc_btn = QPushButton("Clear Localization")
    parent.clear_loc_btn.setStyleSheet(
        f"background-color: {get_button_color('clear')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.clear_loc_btn.setToolTip(
        "Delete the applied global.ini from the game's localization directory, reverting to vanilla game text"
    )
    parent.clear_loc_btn.clicked.connect(parent.clear_localization)
    button_layout.addWidget(parent.clear_loc_btn)

    parent.clear_cache_btn = QPushButton("Clear Cache")
    parent.clear_cache_btn.setStyleSheet(
        f"background-color: {get_button_color('clear')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.clear_cache_btn.setToolTip(
        "Delete all cached source files (base.ini, contracts.ini, etc.) from the local cache directory"
    )
    parent.clear_cache_btn.clicked.connect(parent.clear_cache)
    button_layout.addWidget(parent.clear_cache_btn)

    parent.export_locpack_btn = QPushButton("Export")
    parent.export_locpack_btn.setStyleSheet(
        f"background-color: {get_button_color('open')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.export_locpack_btn.setToolTip(
        "Package the currently-applied global.ini into a zip for sharing. "
        "Click Apply to Game first if you haven't already — Export reads the "
        "applied file, not the in-memory edits."
    )
    parent.export_locpack_btn.clicked.connect(parent.export_locpack)
    button_layout.addWidget(parent.export_locpack_btn)

    parent.help_btn = QPushButton("Help")
    parent.help_btn.setStyleSheet(
        f"background-color: {get_button_color('open')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.help_btn.setCheckable(True)
    parent.help_btn.setToolTip("Toggle the Help side-panel")
    parent.help_btn.clicked.connect(parent.show_help)
    button_layout.addWidget(parent.help_btn)

    parent.tutorial_btn = QPushButton("Tutorial")
    parent.tutorial_btn.setStyleSheet(
        f"background-color: {get_button_color('open')}; color: {get_button_text_color()}; font-weight: bold; padding: 6px;"
    )
    parent.tutorial_btn.setToolTip(
        "Start the guided tour of the workflow — runs automatically on first launch; click here anytime to replay."
    )
    parent.tutorial_btn.clicked.connect(parent._start_tutorial)
    button_layout.addWidget(parent.tutorial_btn)

    button_layout.addStretch()
    layout.addLayout(button_layout)

    # ── Filter row ────────────────────────────────────────────────────────
    filter_layout = QHBoxLayout()

    filter_layout.addWidget(QLabel("Category:"))
    parent.category_combo = QComboBox()
    parent.category_combo.setMinimumWidth(200)
    parent.category_combo.setToolTip(
        "Filter rows by domain (Ships, Ship Items, Missions, Gear, Commodities, Journal, Other). "
        "Categories are derived from the loc-key prefix."
    )
    parent.category_combo.currentTextChanged.connect(parent.apply_filters)
    filter_layout.addWidget(parent.category_combo)

    filter_layout.addWidget(QLabel("Status:"))
    parent.status_combo = QComboBox()
    parent.status_combo.addItems(["All", "Modified", "Enhanced", "Unmodified", "New"])
    parent.status_combo.setMaximumWidth(120)
    parent.status_combo.setToolTip(
        "Filter by status. "
        "Modified = you've set a Custom Value; "
        "Enhanced = produced by the enhancements pipeline (ship stats, mission rewards, etc.); "
        "Unmodified = default text only; "
        "New = key exists only in enhancements/user.ini, not in the base file."
    )
    parent.status_combo.currentTextChanged.connect(parent.apply_filters)
    filter_layout.addWidget(parent.status_combo)

    parent.hide_unmodified_check = QCheckBox("Hide Unmodified")
    parent.hide_unmodified_check.setToolTip(
        "Show only rows where you've set a Custom Value. "
        "Same as the Status filter's Modified option but togglable on its own."
    )
    parent.hide_unmodified_check.stateChanged.connect(parent.apply_filters)
    filter_layout.addWidget(parent.hide_unmodified_check)

    parent.favorites_only_check = QCheckBox("★ Favorites Only")
    parent.favorites_only_check.setToolTip(
        "Show only rows you've starred as favorites. Favorites get a configurable prefix prepended "
        "to their name so they sort to the top of the in-game list."
    )
    parent.favorites_only_check.stateChanged.connect(parent.apply_filters)
    filter_layout.addWidget(parent.favorites_only_check)

    parent.grouped_sort_btn = QPushButton("Group Sort")
    parent.grouped_sort_btn.setToolTip("Sort titles and descriptions together for the same entity")
    parent.grouped_sort_btn.setMaximumWidth(100)
    parent.grouped_sort_btn.clicked.connect(parent._on_grouped_sort)
    filter_layout.addWidget(parent.grouped_sort_btn)

    parent.clear_filters_btn = QPushButton("Clear Filters")
    parent.clear_filters_btn.setMaximumWidth(100)
    parent.clear_filters_btn.setToolTip(
        "Reset every filter (category, status, search, per-column boxes, checkboxes) so the full table is shown."
    )
    parent.clear_filters_btn.clicked.connect(parent.clear_filters)
    filter_layout.addWidget(parent.clear_filters_btn)

    parent.copy_filtered_btn = QPushButton("Copy Filtered")
    parent.copy_filtered_btn.setMaximumWidth(100)
    parent.copy_filtered_btn.setToolTip("Copy all visible filtered rows to clipboard (tab-separated)")
    parent.copy_filtered_btn.clicked.connect(parent.copy_filtered_to_clipboard)
    filter_layout.addWidget(parent.copy_filtered_btn)

    filter_layout.addStretch()
    layout.addLayout(filter_layout)

    return layout


def create_strings_tab(parent: MainWindow) -> QWidget:
    """Create the String Editor tab widget.

    Sets the following attributes on *parent*: ``_model``, ``table``,
    ``filter_header``, ``table_status_label``.
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)

    parent._model = StringTableModel(parent)

    parent.table = QTableView()
    parent.table.setModel(parent._model)

    column_names = ["Category", "Key", "Default Value", "Current Value", "★", "Custom Value", "Status"]
    parent.filter_header = FilterHeaderView(column_names, parent.table, skip_columns={0, 4, 6})
    parent.table.setHorizontalHeader(parent.filter_header)
    parent.filter_header.filter_changed.connect(parent.apply_filters)

    parent.table.setAlternatingRowColors(True)
    parent.table.setSortingEnabled(True)
    parent.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    parent.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    parent.table.customContextMenuRequested.connect(parent.show_context_menu)

    vertical_header = parent.table.verticalHeader()
    if vertical_header is not None:
        vertical_header.setVisible(False)

    header = parent.filter_header
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Category
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Key
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Default Value
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Current Value
    header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # ★
    header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Custom Value
    header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Status

    parent.table.setItemDelegateForColumn(COL_CUSTOM, SelectAllDelegate())
    parent.table.clicked.connect(parent._on_cell_clicked)

    layout.addWidget(parent.table)

    selection_model = parent.table.selectionModel()
    if selection_model is not None:
        selection_model.currentRowChanged.connect(parent._on_preview_row_changed)

    parent.table_status_label = QLabel("No data loaded")
    layout.addWidget(parent.table_status_label)

    return widget


def create_about_tab(parent: MainWindow) -> QWidget:
    """Create the About tab widget.

    Sets the following attributes on *parent*: ``about_browser``,
    ``_check_update_btn``.
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)

    parent.about_browser = QTextBrowser()
    parent.about_browser.setOpenExternalLinks(True)
    render_about_html(parent)
    layout.addWidget(parent.about_browser)

    btn_row = QHBoxLayout()
    parent._check_update_btn = QPushButton("Check for Updates")
    parent._check_update_btn.setMaximumWidth(180)
    parent._check_update_btn.setToolTip("Check whether a newer version of Open Strings is available on GitHub")
    parent._check_update_btn.clicked.connect(lambda: parent._check_for_app_update(manual=True))
    btn_row.addWidget(parent._check_update_btn)
    btn_row.addStretch()
    layout.addLayout(btn_row)

    return widget


def ensure_help_dock(parent: MainWindow) -> QDockWidget:
    """Create the side-docked Help panel on first use and return it.

    Sets the following attributes on *parent*: ``help_dock``,
    ``help_browser`` (on first call only). Idempotent — returns the
    existing dock unchanged on subsequent calls.
    """
    if parent.help_dock is not None:
        return parent.help_dock

    dock = QDockWidget("Help", parent)
    dock.setObjectName("helpDock")  # needed by restoreState
    dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetClosable
        | QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
    )

    parent.help_browser = QTextBrowser(dock)
    parent.help_browser.setOpenExternalLinks(True)
    dock.setWidget(parent.help_browser)

    parent.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    parent.help_dock = dock

    dock.visibilityChanged.connect(parent._on_help_dock_visibility_changed)

    render_help_html(parent)
    return dock


def render_about_html(parent: MainWindow) -> None:
    """(Re)render the About tab HTML using the current palette.

    Forces the browser's palette to the app palette so its chrome tracks
    theme swaps. Called by create_about_tab and after live theme changes.
    """
    from PyQt6.QtWidgets import QApplication

    from src.gui.markdown_renderer import markdown_to_html

    parent.about_browser.setPalette(QApplication.palette())
    try:
        about_path = get_resource_path("ABOUT.md")
        with open(about_path, encoding="utf-8") as f:
            about_content = f.read()
        about_content = about_content.replace("# Open Strings", f"# Open Strings v{get_version()}")
        from PyQt6.QtGui import QPalette

        palette = QApplication.palette()
        parent.about_browser.setHtml(
            markdown_to_html(
                about_content,
                text_color=palette.color(QPalette.ColorRole.Text).name(),
                base_color=palette.color(QPalette.ColorRole.Base).name(),
                link_color=palette.color(QPalette.ColorRole.Link).name(),
            )
        )
    except Exception as e:
        logger.error(f"Error loading ABOUT.md: {e}", exc_info=True)
        parent.about_browser.setHtml(
            f"<h1>About</h1><p>Unable to load about information.</p><p style='color: gray;'>{str(e)}</p>"
        )


def render_help_html(parent: MainWindow) -> None:
    """(Re)render the Help panel HTML using the current palette.

    Falls back to a stub if HELP.md cannot be found so a misconfigured
    build still shows something usable. Called by ensure_help_dock and
    after live theme changes.
    """
    if not hasattr(parent, "help_browser"):
        return

    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QApplication

    from src.gui.markdown_renderer import markdown_to_html

    parent.help_browser.setPalette(QApplication.palette())
    try:
        help_path = get_resource_path("HELP.md")
        with open(help_path, encoding="utf-8") as f:
            help_markdown = f.read()
        palette = QApplication.palette()
        parent.help_browser.setHtml(
            markdown_to_html(
                help_markdown,
                text_color=palette.color(QPalette.ColorRole.Text).name(),
                base_color=palette.color(QPalette.ColorRole.Base).name(),
                link_color=palette.color(QPalette.ColorRole.Link).name(),
            )
        )
    except Exception as e:
        logger.error(f"Error loading HELP.md: {e}", exc_info=True)
        parent.help_browser.setHtml(
            "<h1>Help</h1><p>Help content could not be loaded. "
            "See the About tab or the project README for usage details.</p>"
        )


def apply_branding_styles(parent: MainWindow) -> None:
    """Apply per-theme colours to the title and tagline header labels."""
    parent.title_label.setStyleSheet(f"color: {get_title_color()};")
    parent.tagline_label.setStyleSheet(f"font-size: 11px; letter-spacing: 2px; color: {get_tagline_color()};")
