from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow, QWidget
from src.gui.main_window import MainWindow
from src.gui.string_table_model import COL_CURRENT, COL_STAR
from src.gui.window_setup import create_toolbar
from src.models.string_model import StringEntry
from src.utils.settings import AppSettings

pytestmark = pytest.mark.unit


class _Visibility:
    def __init__(self):
        self.visible = None

    def setVisible(self, visible: bool) -> None:
        self.visible = visible

    def setChecked(self, checked: bool) -> None:
        self.checked = checked

    def blockSignals(self, blocked: bool) -> bool:
        previous = getattr(self, "signals_blocked", False)
        self.signals_blocked = blocked
        return previous


def _window():
    advanced_toolbar = [_Visibility() for _ in range(4)]
    advanced_filters = [_Visibility() for _ in range(7)]
    return (
        SimpleNamespace(
            basic_mode_btn=_Visibility(),
            advanced_mode_btn=_Visibility(),
            _advanced_toolbar_buttons=advanced_toolbar,
            _advanced_filter_widgets=advanced_filters,
            basic_search_label=_Visibility(),
            basic_search_input=_Visibility(),
            filter_header=SimpleNamespace(set_filter_row_visible=Mock()),
            menu_heading_widget=_Visibility(),
            table=SimpleNamespace(setColumnHidden=Mock()),
        ),
        advanced_toolbar,
        advanced_filters,
    )


def test_basic_view_keeps_search_and_hides_advanced_controls():
    window, advanced_toolbar, advanced_filters = _window()

    MainWindow._apply_view_mode(window, AppSettings.VIEW_MODE_BASIC)

    assert window.basic_mode_btn.checked is True
    assert window.advanced_mode_btn.checked is False
    assert window.basic_search_label.visible is True
    assert window.basic_search_input.visible is True
    assert all(not button.visible for button in advanced_toolbar)
    assert all(not control.visible for control in advanced_filters)
    assert window.filter_header.set_filter_row_visible.call_args.args == (False,)
    assert window.menu_heading_widget.visible is False
    window.table.setColumnHidden.assert_any_call(COL_CURRENT, True)
    window.table.setColumnHidden.assert_any_call(COL_STAR, True)


def test_advanced_view_restores_full_controls():
    window, advanced_toolbar, advanced_filters = _window()

    MainWindow._apply_view_mode(window, AppSettings.VIEW_MODE_ADVANCED)

    assert window.basic_mode_btn.checked is False
    assert window.advanced_mode_btn.checked is True
    assert window.basic_search_input.visible is False
    assert all(control.visible for control in advanced_toolbar)
    assert all(control.visible for control in advanced_filters)
    assert window.filter_header.set_filter_row_visible.call_args.args == (True,)
    assert window.menu_heading_widget.visible is True
    window.table.setColumnHidden.assert_any_call(COL_CURRENT, False)
    window.table.setColumnHidden.assert_any_call(COL_STAR, False)


def test_clear_filters_resets_basic_search():
    basic_search = Mock()
    category = Mock()
    category.currentIndex.return_value = 0
    window = SimpleNamespace(
        basic_search_input=basic_search,
        category_combo=category,
        status_combo=Mock(),
        hide_unmodified_check=Mock(),
        favorites_only_check=Mock(),
        filter_header=SimpleNamespace(clear_all=Mock()),
        apply_filters=Mock(),
    )

    MainWindow.clear_filters(window)

    basic_search.clear.assert_called_once()
    window.filter_header.clear_all.assert_called_once()
    window.apply_filters.assert_called_once()


def test_basic_global_search_ignores_hidden_advanced_filters():
    entry = StringEntry(
        key="sample",
        source_file="global",
        category="Ships",
        original_value="stock",
        custom_value="Search me",
        status="Modified",
    )
    window = SimpleNamespace(
        _view_mode=AppSettings.VIEW_MODE_BASIC,
        entries=[entry],
        default_values={},
        filter_header=SimpleNamespace(
            get_filter_texts=lambda: ["", "not this key", "", "", "", "", ""],
            get_filter_modes=lambda: ["contains"] * 7,
        ),
        category_combo=SimpleNamespace(currentText=lambda: "All"),
        status_combo=SimpleNamespace(currentText=lambda: "Unmodified"),
        hide_unmodified_check=SimpleNamespace(isChecked=lambda: True),
        favorites_only_check=SimpleNamespace(isChecked=lambda: True),
        basic_search_input=SimpleNamespace(text=lambda: "search me"),
    )

    assert MainWindow._filtered_entry_indices(window) == [0]


def test_advanced_view_keeps_per_column_filters():
    entries = [
        StringEntry(key="needle", source_file="global", category="Ships", original_value="stock"),
        StringEntry(key="other", source_file="global", category="Ships", original_value="stock"),
    ]
    window = SimpleNamespace(
        _view_mode=AppSettings.VIEW_MODE_ADVANCED,
        entries=entries,
        default_values={},
        filter_header=SimpleNamespace(
            get_filter_texts=lambda: ["", "needle", "", "", "", "", ""],
            get_filter_modes=lambda: ["contains"] * 7,
        ),
        category_combo=SimpleNamespace(currentText=lambda: "All"),
        status_combo=SimpleNamespace(currentText=lambda: "All"),
        hide_unmodified_check=SimpleNamespace(isChecked=lambda: False),
        favorites_only_check=SimpleNamespace(isChecked=lambda: False),
        basic_search_input=SimpleNamespace(text=lambda: "other"),
    )

    assert MainWindow._filtered_entry_indices(window) == [0]


def test_toolbar_mouse_clicks_call_mode_handler(qtbot, monkeypatch):
    window = QMainWindow()
    window.set_view_mode = Mock()
    for name in (
        "open_localization_dir",
        "apply_to_game",
        "restore_backup",
        "clear_localization",
        "clear_cache",
        "export_locpack",
        "show_help",
        "_start_tutorial",
        "apply_filters",
        "_on_grouped_sort",
        "clear_filters",
        "copy_filtered_to_clipboard",
    ):
        setattr(window, name, Mock())
    container = QWidget()
    container.setLayout(create_toolbar(window))
    window.setCentralWidget(container)
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(AppSettings, "set_view_mode", window.set_view_mode)

    assert window.basic_mode_btn.accessibleName() == "Basic view"
    assert window.advanced_mode_btn.accessibleName() == "Advanced view"
    assert window.basic_search_input.accessibleName() == "Search localization strings"
    assert window.category_combo.accessibleName() == "Category filter"
    assert window.status_combo.accessibleName() == "Status filter"

    qtbot.mouseClick(window.basic_mode_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.advanced_mode_btn, Qt.MouseButton.LeftButton)
    window.basic_mode_btn.setChecked(True)
    window.advanced_mode_btn.setChecked(True)

    assert window.set_view_mode.call_args_list == [
        ((AppSettings.VIEW_MODE_BASIC,),),
        ((AppSettings.VIEW_MODE_ADVANCED,),),
        ((AppSettings.VIEW_MODE_BASIC,),),
        ((AppSettings.VIEW_MODE_ADVANCED,),),
    ]
