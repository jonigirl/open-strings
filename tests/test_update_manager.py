"""Tests for UpdateManager."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_manager(qtbot):
    from PyQt6.QtWidgets import QMainWindow
    from src.gui.update_manager import UpdateManager

    window = QMainWindow()
    qtbot.addWidget(window)
    window.status_bar_mgr = MagicMock()

    mgr = UpdateManager(window)
    return mgr, window


def _mock_worker():
    w = MagicMock()
    w.isRunning.return_value = False
    w.wait.return_value = True
    return w


# ── Construction ──────────────────────────────────────────────────────────────


class TestConstruction:
    def test_no_worker_on_init(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        assert mgr._worker is None

    def test_is_running_false_on_init(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        assert not mgr.is_running()


# ── check_for_update throttle ─────────────────────────────────────────────────


class TestThrottle:
    def _patch_settings(self, monkeypatch, last_epoch):
        from src.gui.update_manager import AppSettings

        monkeypatch.setattr(AppSettings, "get_last_update_check_epoch", staticmethod(lambda: last_epoch))

    def test_auto_check_skipped_within_interval(self, qtbot, monkeypatch):
        mgr, _ = _make_manager(qtbot)
        self._patch_settings(monkeypatch, time.time() - 60)  # 1 min ago — within 6h

        with patch("src.gui.update_manager.AppUpdateCheckerWorker") as MockWorker:
            mgr.check_for_update(manual=False)
            MockWorker.assert_not_called()

    def test_auto_check_runs_after_interval(self, qtbot, monkeypatch):
        mgr, _ = _make_manager(qtbot)
        self._patch_settings(monkeypatch, time.time() - 7 * 3600)  # 7h ago — outside interval

        with patch("src.gui.update_manager.AppUpdateCheckerWorker") as MockWorker:
            instance = _mock_worker()
            MockWorker.return_value = instance
            mgr.check_for_update(manual=False)
            instance.start.assert_called_once()

    def test_manual_check_always_runs(self, qtbot, monkeypatch):
        mgr, _ = _make_manager(qtbot)
        self._patch_settings(monkeypatch, time.time() - 60)  # recent — would block auto

        with patch("src.gui.update_manager.AppUpdateCheckerWorker") as MockWorker:
            instance = _mock_worker()
            MockWorker.return_value = instance
            mgr.check_for_update(manual=True)
            instance.start.assert_called_once()

    def test_no_last_check_allows_auto_check(self, qtbot, monkeypatch):
        mgr, _ = _make_manager(qtbot)
        self._patch_settings(monkeypatch, None)  # never checked

        with patch("src.gui.update_manager.AppUpdateCheckerWorker") as MockWorker:
            instance = _mock_worker()
            MockWorker.return_value = instance
            mgr.check_for_update(manual=False)
            instance.start.assert_called_once()

    def test_concurrent_check_is_noop(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = True
        mgr._worker = w

        with patch("src.gui.update_manager.AppUpdateCheckerWorker") as MockWorker:
            mgr.check_for_update(manual=True)
            MockWorker.assert_not_called()


# ── Status bar message on manual check ───────────────────────────────────────


class TestManualCheckMessage:
    def _patch_settings(self, monkeypatch):
        from src.gui.update_manager import AppSettings

        monkeypatch.setattr(AppSettings, "get_last_update_check_epoch", staticmethod(lambda: None))

    def test_manual_check_shows_status_message(self, qtbot, monkeypatch):
        self._patch_settings(monkeypatch)
        mgr, window = _make_manager(qtbot)

        with patch("src.gui.update_manager.AppUpdateCheckerWorker") as MockWorker:
            instance = _mock_worker()
            MockWorker.return_value = instance
            mgr.check_for_update(manual=True)

        window.status_bar_mgr.show_message.assert_called_with("Checking for updates…")

    def test_auto_check_does_not_show_status_message(self, qtbot, monkeypatch):
        self._patch_settings(monkeypatch)
        mgr, window = _make_manager(qtbot)

        with patch("src.gui.update_manager.AppUpdateCheckerWorker") as MockWorker:
            instance = _mock_worker()
            MockWorker.return_value = instance
            mgr.check_for_update(manual=False)

        window.status_bar_mgr.show_message.assert_not_called()


# ── _on_finished ──────────────────────────────────────────────────────────────


class TestOnFinished:
    def test_no_update_manual_shows_up_to_date(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = True

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.information = MagicMock()
            mgr._on_finished(False, "1.0.0", "")
            MockMsgBox.information.assert_called_once()

    def test_no_update_auto_shows_nothing(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = False

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.information = MagicMock()
            mgr._on_finished(False, "1.0.0", "")
            MockMsgBox.information.assert_not_called()

    def test_manual_finished_shows_ready_message(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = True

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.information = MagicMock()
            mgr._on_finished(False, "1.0.0", "")

        window.status_bar_mgr.show_message.assert_called_with("Ready")

    def test_auto_finished_does_not_show_ready(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = False

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.information = MagicMock()
            mgr._on_finished(False, "1.0.0", "")

        window.status_bar_mgr.show_message.assert_not_called()

    def test_finished_clears_worker(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = False

        with patch("src.gui.update_manager.QMessageBox"):
            mgr._on_finished(False, "1.0.0", "")

        assert mgr._worker is None


# ── _on_error ─────────────────────────────────────────────────────────────────


class TestOnError:
    def test_manual_error_shows_warning(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = True

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.warning = MagicMock()
            mgr._on_error("timeout")
            MockMsgBox.warning.assert_called_once()

    def test_auto_error_shows_nothing(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = False

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.warning = MagicMock()
            mgr._on_error("timeout")
            MockMsgBox.warning.assert_not_called()

    def test_manual_error_shows_ready(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = True

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.warning = MagicMock()
            mgr._on_error("timeout")

        window.status_bar_mgr.show_message.assert_called_with("Ready")

    def test_auto_error_does_not_show_ready(self, qtbot):
        mgr, window = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = False

        with patch("src.gui.update_manager.QMessageBox") as MockMsgBox:
            MockMsgBox.warning = MagicMock()
            mgr._on_error("timeout")

        window.status_bar_mgr.show_message.assert_not_called()

    def test_error_clears_worker(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr._worker = _mock_worker()
        mgr._manual = False

        with patch("src.gui.update_manager.QMessageBox"):
            mgr._on_error("fail")

        assert mgr._worker is None


# ── cleanup ───────────────────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_quits_running_worker(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = True
        mgr._worker = w
        mgr.cleanup()
        w.quit.assert_called_once()

    def test_cleanup_noop_when_no_worker(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr.cleanup()  # should not raise

    def test_cleanup_noop_when_worker_stopped(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = False
        mgr._worker = w
        mgr.cleanup()
        w.quit.assert_not_called()
