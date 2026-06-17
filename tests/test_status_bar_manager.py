"""Tests for StatusBarManager — no full Qt application loop required.

These tests use pytest-qt's ``qtbot`` fixture which provides a minimal
QApplication, letting us instantiate QMainWindow, QStatusBar, and QLabel
widgets and assert on their state without launching the full UI.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_manager(qtbot):
    """Return a (StatusBarManager, QMainWindow) pair backed by a real Qt window."""
    from PyQt6.QtWidgets import QMainWindow
    from src.gui.status_bar_manager import StatusBarManager

    window = QMainWindow()
    qtbot.addWidget(window)
    mgr = StatusBarManager(window)
    return mgr, window


# ── Construction ──────────────────────────────────────────────────────────────


class TestConstruction:
    def test_no_widgets_before_install(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        assert mgr._spinner_label is None
        assert mgr._channel_indicator is None
        assert mgr._app_version_indicator is None

    def test_source_status_starts_empty(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        assert mgr._source_status == {}

    def test_spinner_timer_starts_none(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        assert mgr._spinner_timer is None


# ── install_widgets ───────────────────────────────────────────────────────────


class TestInstallWidgets:
    def test_install_creates_spinner_label(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        assert mgr._spinner_label is not None

    def test_install_creates_channel_indicator(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        assert mgr._channel_indicator is not None

    def test_install_creates_app_version_indicator(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        assert mgr._app_version_indicator is not None

    def test_install_creates_spinner_timer(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        assert mgr._spinner_timer is not None

    def test_spinner_starts_hidden(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        assert mgr._spinner_label is not None
        assert not mgr._spinner_label.isVisible()

    def test_install_idempotent(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        label_id_before = id(mgr._spinner_label)
        mgr.install_widgets()
        assert id(mgr._spinner_label) == label_id_before

    def test_app_version_label_contains_version(self, qtbot):
        from src.utils.version import get_version

        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        assert mgr._app_version_indicator is not None
        assert f"v{get_version()}" in mgr._app_version_indicator.text()


# ── Spinner ───────────────────────────────────────────────────────────────────


class TestSpinner:
    def test_start_spinner_makes_label_visible(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()
        # The window must be shown for Qt to propagate visible=True through the
        # widget hierarchy; without it isVisible() always returns False.
        window.show()
        mgr.start_spinner()
        assert mgr._spinner_label is not None
        assert mgr._spinner_label.isVisible()

    def test_start_spinner_sets_first_frame(self, qtbot):
        from src.gui.status_bar_manager import _SPINNER_FRAMES

        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.start_spinner()
        assert mgr._spinner_label is not None
        assert mgr._spinner_label.text() == _SPINNER_FRAMES[0]
        assert mgr._spinner_frame == 0

    def test_stop_spinner_hides_label(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()
        window.show()
        mgr.start_spinner()
        mgr.stop_spinner()
        assert mgr._spinner_label is not None
        assert not mgr._spinner_label.isVisible()

    def test_tick_advances_frame(self, qtbot):
        from src.gui.status_bar_manager import _SPINNER_FRAMES

        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.start_spinner()
        mgr._tick_spinner()
        assert mgr._spinner_frame == 1
        assert mgr._spinner_label is not None
        assert mgr._spinner_label.text() == _SPINNER_FRAMES[1]

    def test_tick_wraps_around(self, qtbot):
        from src.gui.status_bar_manager import _SPINNER_FRAMES

        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.start_spinner()
        for _ in range(len(_SPINNER_FRAMES)):
            mgr._tick_spinner()
        assert mgr._spinner_frame == 0

    def test_start_stop_before_install_is_safe(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.start_spinner()  # no crash — widgets are None
        mgr.stop_spinner()


# ── Channel indicator ─────────────────────────────────────────────────────────


class TestChannelIndicator:
    def test_refresh_before_install_is_safe(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.refresh_channel_indicator()  # should not raise

    def test_channel_text_after_install(self, qtbot, monkeypatch):
        from src.gui.status_bar_manager import AppSettings

        monkeypatch.setattr(AppSettings, "get_active_channel", staticmethod(lambda: "LIVE"))
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        assert mgr._channel_indicator is not None
        assert "LIVE" in mgr._channel_indicator.text()

    def test_refresh_updates_text(self, qtbot, monkeypatch):
        from src.gui.status_bar_manager import AppSettings

        monkeypatch.setattr(AppSettings, "get_active_channel", staticmethod(lambda: "PTU"))
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.refresh_channel_indicator()
        assert mgr._channel_indicator is not None
        assert "PTU" in mgr._channel_indicator.text()


# ── set_source_status / update_status ────────────────────────────────────────


class TestStatusComposition:
    def _minimal_monkeypatch(self, monkeypatch):
        """Patch AppSettings to provide minimal stable values for status tests."""
        from src.gui.status_bar_manager import AppSettings

        monkeypatch.setattr(AppSettings, "get_merge_hierarchy", staticmethod(lambda: ["global", "user"]))
        monkeypatch.setattr(AppSettings, "get_game_version", staticmethod(lambda: None))
        monkeypatch.setattr(AppSettings, "get_active_channel", staticmethod(lambda: "LIVE"))
        monkeypatch.setattr(AppSettings, "get_channel_install_path", staticmethod(lambda: None))

    def test_set_source_status_stores_value(self, qtbot, monkeypatch):
        self._minimal_monkeypatch(monkeypatch)
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.set_source_status("global", "Global: 4.8.0 ✓")
        assert mgr._source_status["global"] == "Global: 4.8.0 ✓"

    def test_update_status_shows_ready_when_empty(self, qtbot, monkeypatch):
        self._minimal_monkeypatch(monkeypatch)
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.update_status(entries=None, has_running_worker=False)
        assert window.statusBar().currentMessage() == "Ready"

    def test_update_status_suppresses_ready_when_worker_running(self, qtbot, monkeypatch):
        self._minimal_monkeypatch(monkeypatch)
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()
        # Ensure statusBar exists and has no message
        window.statusBar().showMessage("")
        mgr.update_status(entries=None, has_running_worker=True)
        # "Ready" must not be written while a worker is active
        assert window.statusBar().currentMessage() != "Ready"

    def test_update_status_shows_source_status(self, qtbot, monkeypatch):
        self._minimal_monkeypatch(monkeypatch)
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.set_source_status("global", "Global: 4.8.0 ✓")
        mgr.update_status(entries=None, has_running_worker=False)
        assert "Global: 4.8.0 ✓" in window.statusBar().currentMessage()

    def test_update_status_shows_entry_count(self, qtbot, monkeypatch):
        from unittest.mock import MagicMock

        self._minimal_monkeypatch(monkeypatch)
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()

        entry = MagicMock()
        entry.status = "Unmodified"
        entries = [entry] * 100

        mgr.update_status(entries=entries, has_running_worker=False)
        assert "100" in window.statusBar().currentMessage()

    def test_update_status_shows_override_count_when_nonzero(self, qtbot, monkeypatch):
        from unittest.mock import MagicMock

        self._minimal_monkeypatch(monkeypatch)
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()

        e_modified = MagicMock()
        e_modified.status = "Modified"
        e_normal = MagicMock()
        e_normal.status = "Unmodified"
        entries = [e_modified, e_modified, e_normal]

        mgr.update_status(entries=entries, has_running_worker=False)
        msg = window.statusBar().currentMessage()
        assert "2 overrides" in msg

    def test_update_status_no_override_label_when_zero(self, qtbot, monkeypatch):
        from unittest.mock import MagicMock

        self._minimal_monkeypatch(monkeypatch)
        mgr, window = _make_manager(qtbot)
        mgr.install_widgets()

        entry = MagicMock()
        entry.status = "Unmodified"
        entries = [entry]

        mgr.update_status(entries=entries, has_running_worker=False)
        assert "overrides" not in window.statusBar().currentMessage()

    def test_show_message_delegates_to_status_bar(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr.show_message("Hello test")
        assert window.statusBar().currentMessage() == "Hello test"


# ── cleanup ───────────────────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_stops_timer(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.install_widgets()
        mgr.start_spinner()
        assert mgr._spinner_timer is not None
        assert mgr._spinner_timer.isActive()
        mgr.cleanup()
        assert not mgr._spinner_timer.isActive()

    def test_cleanup_before_install_is_safe(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.cleanup()  # no crash
