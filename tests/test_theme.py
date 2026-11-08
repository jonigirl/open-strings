from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from src.gui import main_window
from src.gui.theme import THEME_DARK, THEME_LIGHT, THEME_OS_DARK, get_effective_theme

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("color_scheme", "expected"),
    [
        (Qt.ColorScheme.Light, THEME_LIGHT),
        (Qt.ColorScheme.Dark, THEME_OS_DARK),
        (Qt.ColorScheme.Unknown, THEME_OS_DARK),
    ],
)
def test_default_theme_follows_system_color_scheme(color_scheme, expected):
    assert get_effective_theme(THEME_OS_DARK, color_scheme=color_scheme) == expected


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_explicit_theme_ignores_system_color_scheme(theme):
    assert (
        get_effective_theme(theme, color_scheme=Qt.ColorScheme.Dark if theme == THEME_LIGHT else Qt.ColorScheme.Light)
        == theme
    )


@pytest.mark.parametrize(
    ("theme", "should_refresh"),
    [(THEME_OS_DARK, True), (THEME_LIGHT, False), (THEME_DARK, False)],
)
def test_system_color_change_refreshes_only_default(theme, should_refresh, monkeypatch):
    scheduled = []
    window = SimpleNamespace(_refresh_system_theme=Mock())
    monkeypatch.setattr(main_window.AppSettings, "get_theme", lambda: theme)
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))

    main_window.MainWindow._on_system_color_scheme_changed(window, Qt.ColorScheme.Light)

    if should_refresh:
        assert scheduled == [(0, window._refresh_system_theme)]
    else:
        assert scheduled == []


def test_system_theme_refresh_reapplies_theme_and_repaints(monkeypatch, qtbot):
    app = main_window.QApplication.instance()
    assert app is not None
    worker_coord = SimpleNamespace(refresh_theme=Mock())
    window = SimpleNamespace(refresh_action_buttons=Mock(), worker_coord=worker_coord)
    apply_theme = Mock()
    monkeypatch.setattr(main_window.AppSettings, "get_theme", lambda: THEME_OS_DARK)
    monkeypatch.setattr(main_window, "apply_theme", apply_theme)

    main_window.MainWindow._refresh_system_theme(window)

    apply_theme.assert_called_once_with(app, THEME_OS_DARK)
    window.refresh_action_buttons.assert_called_once_with()
    worker_coord.refresh_theme.assert_called_once_with()


def test_refresh_action_buttons_updates_tutorial_button_theme(monkeypatch):
    monkeypatch.setattr(main_window, "get_button_color", lambda role: f"{role}-color")
    monkeypatch.setattr(main_window, "get_button_text_color", lambda: "button-text")
    viewport = SimpleNamespace(update=Mock())
    window = SimpleNamespace(
        _apply_branding_styles=Mock(),
        open_loc_dir_btn=Mock(),
        apply_btn=Mock(),
        restore_backup_btn=Mock(),
        clear_loc_btn=Mock(),
        clear_cache_btn=Mock(),
        export_locpack_btn=Mock(),
        help_btn=Mock(),
        tutorial_btn=Mock(),
        table=SimpleNamespace(currentIndex=lambda: QModelIndex(), viewport=lambda: viewport),
    )

    main_window.MainWindow.refresh_action_buttons(window)

    window.tutorial_btn.setStyleSheet.assert_called_once_with(
        "background-color: open-color; color: button-text; font-weight: bold; padding: 6px;"
    )
    viewport.update.assert_called_once_with()
