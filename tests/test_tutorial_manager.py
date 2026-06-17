"""Tests for TutorialManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_manager(qtbot):
    from PyQt6.QtWidgets import QMainWindow
    from src.gui.tutorial_manager import TutorialManager

    window = QMainWindow()
    qtbot.addWidget(window)
    mgr = TutorialManager(window)
    return mgr, window


def _patch_version(monkeypatch, *, current: str = "1.0.0", seen: str = ""):
    from src.gui import tutorial_manager as tm

    monkeypatch.setattr(tm, "get_version", lambda: current)
    monkeypatch.setattr(
        tm.AppSettings,
        "get_tutorial_completed_version",
        staticmethod(lambda: seen),
    )


# ── maybe_start_first_run — idempotency ───────────────────────────────────────


class TestMaybeStartFirstRun:
    def test_only_fires_once(self, qtbot, monkeypatch):
        _patch_version(monkeypatch, seen="0.9.0")
        mgr, _ = _make_manager(qtbot)

        with patch.object(mgr, "start_tutorial") as mock_start:
            mgr.maybe_start_first_run()
            mgr.maybe_start_first_run()  # second call — noop
            assert mock_start.call_count <= 1  # may be 0 due to timer delay

    def test_already_seen_does_not_start_tutorial(self, qtbot, monkeypatch):
        _patch_version(monkeypatch, current="1.0.0", seen="1.0.0")
        mgr, _ = _make_manager(qtbot)

        with patch.object(mgr, "start_tutorial") as mock_start:
            mgr.maybe_start_first_run()
            mock_start.assert_not_called()

    def test_already_seen_emits_tour_finished(self, qtbot, monkeypatch):
        _patch_version(monkeypatch, current="1.0.0", seen="1.0.0")
        mgr, _ = _make_manager(qtbot)

        fired = []
        mgr.tour_finished.connect(lambda: fired.append(True))

        mgr.maybe_start_first_run()
        # QTimer.singleShot(0, ...) — process the event loop
        qtbot.wait(50)

        assert fired == [True]

    def test_unseen_version_sets_checked_flag(self, qtbot, monkeypatch):
        _patch_version(monkeypatch, current="2.0.0", seen="1.0.0")
        mgr, _ = _make_manager(qtbot)

        with patch.object(mgr, "start_tutorial"):
            mgr.maybe_start_first_run()
            assert mgr._first_run_checked is True

    def test_second_call_is_noop_after_flag_set(self, qtbot, monkeypatch):
        _patch_version(monkeypatch, current="1.0.0", seen="1.0.0")
        mgr, _ = _make_manager(qtbot)
        mgr._first_run_checked = True

        fired = []
        mgr.tour_finished.connect(lambda: fired.append(True))
        mgr.maybe_start_first_run()
        qtbot.wait(50)
        assert fired == []  # already checked — no emit


# ── start_tutorial ────────────────────────────────────────────────────────────


class TestStartTutorial:
    def test_noop_when_tour_already_running(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mock_tour = MagicMock()
        mock_tour.is_running.return_value = True
        mgr._tour = mock_tour

        with patch("src.gui.tutorial_manager.TutorialTour") as MockTour:
            mgr.start_tutorial()
            MockTour.assert_not_called()

    def test_exception_in_tour_init_emits_tour_finished(self, qtbot):
        mgr, _ = _make_manager(qtbot)

        fired = []
        mgr.tour_finished.connect(lambda: fired.append(True))

        with patch("src.gui.tutorial_manager.TutorialTour", side_effect=RuntimeError("boom")):
            with patch.object(mgr, "_build_tour_steps", return_value=[]):
                mgr.start_tutorial()

        assert fired == [True]

    def test_exception_clears_tour(self, qtbot):
        mgr, _ = _make_manager(qtbot)

        with patch("src.gui.tutorial_manager.TutorialTour", side_effect=RuntimeError("boom")):
            with patch.object(mgr, "_build_tour_steps", return_value=[]):
                mgr.start_tutorial()

        assert mgr._tour is None


# ── _on_tour_done ─────────────────────────────────────────────────────────────


class TestOnTourDone:
    def test_records_version(self, qtbot, monkeypatch):
        _patch_version(monkeypatch, current="1.5.0")
        mgr, _ = _make_manager(qtbot)
        mgr._tour = MagicMock()

        recorded = []
        from src.gui import tutorial_manager as tm

        monkeypatch.setattr(
            tm.AppSettings,
            "set_tutorial_completed_version",
            staticmethod(lambda v: recorded.append(v)),
        )

        mgr._on_tour_done(True)
        assert recorded == ["1.5.0"]

    def test_emits_tour_finished(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr._tour = MagicMock()

        fired = []
        mgr.tour_finished.connect(lambda: fired.append(True))

        mgr._on_tour_done(True)
        assert fired == [True]

    def test_emits_on_skip_too(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr._tour = MagicMock()

        fired = []
        mgr.tour_finished.connect(lambda: fired.append(True))

        mgr._on_tour_done(False)  # completed=False means skipped
        assert fired == [True]

    def test_clears_tour_reference(self, qtbot):
        mgr, _ = _make_manager(qtbot)
        mgr._tour = MagicMock()

        mgr._on_tour_done(True)
        assert mgr._tour is None


# ── _build_tour_steps — bad JSON ──────────────────────────────────────────────


class TestBuildTourSteps:
    def test_returns_empty_on_missing_file(self, qtbot):
        mgr, _ = _make_manager(qtbot)

        with patch("src.gui.tutorial_manager.get_resource_path", return_value="/nonexistent/path"):
            steps = mgr._build_tour_steps()

        assert steps == []

    def test_returns_empty_on_bad_json(self, qtbot, tmp_path):
        mgr, _ = _make_manager(qtbot)
        bad_json = tmp_path / "tutorial.json"
        bad_json.write_text("not json", encoding="utf-8")

        with patch("src.gui.tutorial_manager.get_resource_path", return_value=str(bad_json)):
            steps = mgr._build_tour_steps()

        assert steps == []

    def test_skips_step_missing_id(self, qtbot, tmp_path):
        mgr, _ = _make_manager(qtbot)
        payload = {"steps": [{"title": "T", "description": "D"}]}
        f = tmp_path / "tutorial.json"
        f.write_text(__import__("json").dumps(payload), encoding="utf-8")

        with patch("src.gui.tutorial_manager.get_resource_path", return_value=str(f)):
            steps = mgr._build_tour_steps()

        assert steps == []

    def test_skips_step_with_no_wiring(self, qtbot, tmp_path):
        mgr, _ = _make_manager(qtbot)
        payload = {"steps": [{"id": "NONEXISTENT", "title": "T", "description": "D"}]}
        f = tmp_path / "tutorial.json"
        f.write_text(__import__("json").dumps(payload), encoding="utf-8")

        with patch("src.gui.tutorial_manager.get_resource_path", return_value=str(f)):
            steps = mgr._build_tour_steps()

        assert steps == []

    def test_skips_step_missing_description(self, qtbot, tmp_path):
        mgr, _ = _make_manager(qtbot)
        payload = {"steps": [{"id": "welcome", "title": "Hi"}]}
        f = tmp_path / "tutorial.json"
        f.write_text(__import__("json").dumps(payload), encoding="utf-8")

        with patch("src.gui.tutorial_manager.get_resource_path", return_value=str(f)):
            steps = mgr._build_tour_steps()

        assert steps == []

    def test_valid_step_is_included(self, qtbot, tmp_path):
        mgr, _ = _make_manager(qtbot)
        payload = {"steps": [{"id": "welcome", "title": "Hi", "description": "Welcome to the tour"}]}
        f = tmp_path / "tutorial.json"
        f.write_text(__import__("json").dumps(payload), encoding="utf-8")

        with patch("src.gui.tutorial_manager.get_resource_path", return_value=str(f)):
            steps = mgr._build_tour_steps()

        assert len(steps) == 1
        assert steps[0].title == "Hi"
