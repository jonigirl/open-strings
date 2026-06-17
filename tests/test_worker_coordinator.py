"""Tests for WorkerCoordinator — lifecycle, signals, and cleanup.

Workers do real I/O; these tests mock the worker classes so only the
coordinator's lifecycle logic (create, wire, start, cleanup, signal
emission) is exercised without touching the filesystem.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_coordinator(qtbot):
    """Return a (WorkerCoordinator, QMainWindow) pair."""
    from PyQt6.QtWidgets import QMainWindow
    from src.gui.worker_coordinator import WorkerCoordinator

    window = QMainWindow()
    qtbot.addWidget(window)

    # Minimal status_bar_mgr stub so coordinator can call show_message
    window.status_bar_mgr = MagicMock()
    # start_spinner / stop_spinner are MainWindow methods; stub them
    window.start_spinner = MagicMock()
    window.stop_spinner = MagicMock()

    coord = WorkerCoordinator(window)
    return coord, window


def _mock_worker():
    """Return a MagicMock that looks like a QThread-based worker."""
    w = MagicMock()
    w.isRunning.return_value = False
    return w


# ── Construction ──────────────────────────────────────────────────────────────


class TestConstruction:
    def test_no_active_workers_on_init(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        assert not coord.has_active_worker()

    def test_all_worker_slots_are_none(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        assert coord._loader_worker is None
        assert coord._p4k_worker is None
        assert coord._forge_worker is None
        assert coord._enhancements_worker is None
        assert coord._startup_sync_worker is None

    def test_all_progress_dialogs_are_none(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        assert coord._loading_progress is None
        assert coord._startup_progress is None
        assert coord._p4k_progress is None
        assert coord._forge_progress_dialog is None
        assert coord._enhancements_progress_dialog is None


# ── has_active_worker ─────────────────────────────────────────────────────────


class TestHasActiveWorker:
    def test_false_when_all_none(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        assert not coord.has_active_worker()

    def test_true_when_loader_running(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = True
        coord._loader_worker = w
        assert coord.has_active_worker()

    def test_true_when_p4k_running(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = True
        coord._p4k_worker = w
        assert coord.has_active_worker()

    def test_true_when_enhancements_running(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = True
        coord._enhancements_worker = w
        assert coord.has_active_worker()

    def test_false_when_workers_present_but_not_running(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._loader_worker = _mock_worker()  # isRunning() returns False
        coord._p4k_worker = _mock_worker()
        assert not coord.has_active_worker()


# ── cleanup_all ───────────────────────────────────────────────────────────────


class TestCleanupAll:
    def test_cleanup_calls_quit_and_wait(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = True
        w.wait.return_value = True  # finished within timeout
        coord._loader_worker = w
        coord.cleanup_all()
        w.quit.assert_called_once()
        w.wait.assert_called_once()

    def test_cleanup_calls_cancel_if_available(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = True
        w.wait.return_value = True
        coord._p4k_worker = w
        coord.cleanup_all()
        w.cancel.assert_called_once()

    def test_cleanup_skips_stopped_workers(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        w = _mock_worker()
        w.isRunning.return_value = False  # already stopped
        coord._loader_worker = w
        coord.cleanup_all()
        w.quit.assert_not_called()

    def test_cleanup_all_none_is_safe(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord.cleanup_all()  # should not raise

    def test_cleanup_multiple_workers(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        workers = [_mock_worker() for _ in range(3)]
        for w in workers:
            w.isRunning.return_value = True
            w.wait.return_value = True
        coord._loader_worker, coord._p4k_worker, coord._forge_worker = workers
        coord.cleanup_all()
        for w in workers:
            w.quit.assert_called_once()


# ── start_file_loading ────────────────────────────────────────────────────────


class TestStartFileLoading:
    def test_loading_finished_signal_emitted(self, qtbot):
        """_on_loading_done should emit loading_finished with correct args."""
        coord, _ = _make_coordinator(qtbot)
        coord._loader_worker = _mock_worker()

        received = []
        coord.loading_finished.connect(lambda e, d, s: received.append((e, d, s)))

        coord._on_loading_done([1, 2], {"k": "v"}, ["s1"])
        assert len(received) == 1
        assert received[0] == ([1, 2], {"k": "v"}, ["s1"])

    def test_loading_error_signal_emitted(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._loader_worker = _mock_worker()

        errors = []
        coord.loading_error.connect(errors.append)

        coord._on_loading_err("oh no")
        assert errors == ["oh no"]

    def test_loading_done_clears_worker(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._loader_worker = _mock_worker()
        coord._on_loading_done([], {}, [])
        assert coord._loader_worker is None

    def test_loading_err_clears_worker(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._loader_worker = _mock_worker()
        coord._on_loading_err("error")
        assert coord._loader_worker is None


# ── start_p4k_extraction ──────────────────────────────────────────────────────


class TestP4kExtraction:
    def test_p4k_finished_signal_emitted_on_success(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._p4k_worker = _mock_worker()
        coord._p4k_progress = MagicMock()

        results = []
        coord.p4k_finished.connect(results.append)

        coord._on_p4k_done(True)
        assert results == [True]

    def test_p4k_finished_signal_emitted_on_failure(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._p4k_worker = _mock_worker()
        coord._p4k_progress = MagicMock()

        results = []
        coord.p4k_finished.connect(results.append)

        coord._on_p4k_done(False)
        assert results == [False]

    def test_p4k_done_stops_spinner(self, qtbot):
        coord, window = _make_coordinator(qtbot)
        coord._p4k_worker = _mock_worker()
        coord._p4k_progress = MagicMock()

        coord._on_p4k_done(True)
        window.stop_spinner.assert_called_once()

    def test_p4k_done_closes_progress_dialog(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._p4k_worker = _mock_worker()
        progress_mock = MagicMock()
        coord._p4k_progress = progress_mock

        coord._on_p4k_done(True)
        progress_mock.close.assert_called_once()
        assert coord._p4k_progress is None

    def test_p4k_noop_if_already_running(self, qtbot):
        """start_p4k_extraction should no-op when a worker already exists."""
        coord, _ = _make_coordinator(qtbot)
        coord._p4k_worker = _mock_worker()

        # Should return early without creating another worker
        with patch("src.gui.worker_coordinator.WorkerCoordinator._ensure_tools_downloaded") as mock_tools:
            coord.start_p4k_extraction()
            mock_tools.assert_not_called()


# ── DataForge extraction ──────────────────────────────────────────────────────


class TestDataforgeExtraction:
    def test_dataforge_finished_signal_on_success(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._forge_worker = _mock_worker()
        coord._forge_progress_dialog = MagicMock()

        results = []
        coord.dataforge_finished.connect(results.append)

        coord._on_dataforge_done(True)
        assert results == [True]

    def test_dataforge_done_stops_spinner(self, qtbot):
        coord, window = _make_coordinator(qtbot)
        coord._forge_worker = _mock_worker()
        coord._forge_progress_dialog = MagicMock()

        coord._on_dataforge_done(True)
        window.stop_spinner.assert_called_once()

    def test_dataforge_done_clears_worker(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._forge_worker = _mock_worker()
        coord._forge_progress_dialog = MagicMock()

        coord._on_dataforge_done(True)
        assert coord._forge_worker is None

    def test_noop_if_forge_already_running(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._forge_worker = _mock_worker()
        with patch("src.gui.worker_coordinator.WorkerCoordinator._ensure_tools_downloaded") as mock_tools:
            coord.start_dataforge_extraction()
            mock_tools.assert_not_called()


# ── Enhancements generation ───────────────────────────────────────────────────


class TestEnhancementsGeneration:
    def test_enhancements_finished_signal(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._enhancements_worker = _mock_worker()
        coord._enhancements_progress_dialog = MagicMock()

        results = []
        coord.enhancements_finished.connect(results.append)

        coord._on_enhancements_done(True)
        assert results == [True]

    def test_enhancements_error_signal(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._enhancements_progress_dialog = MagicMock()

        errors = []
        coord.enhancements_error.connect(errors.append)

        coord._on_enhancements_err("something broke")
        assert errors == ["something broke"]

    def test_enhancements_done_stops_spinner(self, qtbot):
        coord, window = _make_coordinator(qtbot)
        coord._enhancements_worker = _mock_worker()
        coord._enhancements_progress_dialog = MagicMock()

        coord._on_enhancements_done(False)
        window.stop_spinner.assert_called_once()

    def test_enhancements_done_clears_worker(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._enhancements_worker = _mock_worker()
        coord._enhancements_progress_dialog = MagicMock()

        coord._on_enhancements_done(True)
        assert coord._enhancements_worker is None

    def test_noop_if_enhancements_already_running(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._enhancements_worker = _mock_worker()
        with patch("src.utils.settings.AppSettings.get_enabled_enhancement_categories", return_value=set()):
            coord.start_enhancements_generation()
        assert coord._enhancements_worker is not None  # original mock, not replaced


# ── Startup sync ──────────────────────────────────────────────────────────────


class TestStartupSync:
    def _patch_no_remote(self, monkeypatch):
        from src.gui.worker_coordinator import AppSettings

        monkeypatch.setattr(AppSettings, "is_source_enabled", staticmethod(lambda name: False))

    def test_startup_sync_finished_emitted_immediately_when_no_remote(self, qtbot, monkeypatch):
        self._patch_no_remote(monkeypatch)
        coord, _ = _make_coordinator(qtbot)

        fired = []
        coord.startup_sync_finished.connect(lambda: fired.append(True))

        coord.start_startup_sync()
        assert fired == [True]

    def test_startup_sync_done_emits_finished(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._startup_sync_worker = _mock_worker()

        fired = []
        coord.startup_sync_finished.connect(lambda: fired.append(True))

        coord._on_startup_sync_done()
        assert fired == [True]

    def test_startup_sync_done_clears_worker(self, qtbot):
        coord, _ = _make_coordinator(qtbot)
        coord._startup_sync_worker = _mock_worker()
        coord._on_startup_sync_done()
        assert coord._startup_sync_worker is None

    def test_startup_source_starting_emits_signal(self, qtbot):
        coord, _ = _make_coordinator(qtbot)

        names = []
        coord.startup_source_starting.connect(names.append)

        coord._on_startup_source_starting("global")
        assert names == ["global"]

    def test_startup_source_synced_emits_signal(self, qtbot):
        coord, _ = _make_coordinator(qtbot)

        results = []
        coord.startup_source_synced.connect(lambda n, u: results.append((n, u)))

        coord._on_startup_source_synced("global", True)
        assert results == [("global", True)]

    def test_startup_source_error_emits_signal(self, qtbot):
        coord, _ = _make_coordinator(qtbot)

        errors = []
        coord.startup_source_error.connect(lambda n, m: errors.append((n, m)))

        coord._on_startup_source_error("global", "timeout")
        assert errors == [("global", "timeout")]
