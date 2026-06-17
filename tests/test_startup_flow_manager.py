"""Tests for src.gui.startup_flow_manager — non-dialog early-return paths."""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox
from src.gui.startup_flow_manager import StartupFlowManager

pytestmark = pytest.mark.unit


def _make_manager(tmp_path, *, worker_active=False):
    """Create a StartupFlowManager with mocked collaborators."""
    worker_coord = MagicMock()
    worker_coord.has_active_worker.return_value = worker_active
    enhancements_tab = MagicMock()
    mgr = StartupFlowManager(None, worker_coord, enhancements_tab)
    return mgr, worker_coord, enhancements_tab


# ─────────────────────────────────────────────────────────────────────────────
# State flag management
# ─────────────────────────────────────────────────────────────────────────────


class TestStartupFlowManagerState:
    def test_initial_state_flags_are_false(self):
        mgr, _, _ = _make_manager(None)
        assert mgr.enhancements_prompted is False
        assert mgr.check_enhancements_after_loading is False

    def test_reset_startup_state_clears_enhancements_prompted(self):
        mgr, _, _ = _make_manager(None)
        mgr.enhancements_prompted = True
        mgr.reset_startup_state()
        assert mgr.enhancements_prompted is False

    def test_reset_startup_state_does_not_clear_check_enhancements_after_loading(self):
        mgr, _, _ = _make_manager(None)
        mgr.check_enhancements_after_loading = True
        mgr.reset_startup_state()
        assert mgr.check_enhancements_after_loading is True


# ─────────────────────────────────────────────────────────────────────────────
# check_p4k_freshness — early returns that do not show dialogs
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckP4kFreshness:
    def test_returns_false_when_p4k_path_does_not_exist(self, tmp_path):
        mgr, _, _ = _make_manager(tmp_path)
        with patch("src.utils.settings.AppSettings.get_p4k_path", return_value=tmp_path / "missing.p4k"):
            result = mgr.check_p4k_freshness()
        assert result is False

    def test_returns_false_when_base_ini_exists_and_is_fresh(self, tmp_path):
        mgr, _, _ = _make_manager(tmp_path)
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        base_ini = tmp_path / "base.ini"
        base_ini.write_text("k=v", encoding="utf-8")
        # Make base.ini newer than the p4k file so "p4k_newer" is False
        import os
        import time

        future = time.time() + 3600
        os.utime(base_ini, (future, future))
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
        ):
            result = mgr.check_p4k_freshness()
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# maybe_prompt_dataforge_refresh — early returns
# ─────────────────────────────────────────────────────────────────────────────


class TestMaybePromptDataforgeRefresh:
    def test_no_op_when_worker_active(self, tmp_path):
        mgr, worker_coord, _ = _make_manager(tmp_path, worker_active=True)
        mgr.maybe_prompt_dataforge_refresh()
        worker_coord.start_dataforge_extraction.assert_not_called()

    def test_no_op_when_p4k_missing(self, tmp_path):
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with patch("src.utils.settings.AppSettings.get_p4k_path", return_value=tmp_path / "missing.p4k"):
            mgr.maybe_prompt_dataforge_refresh()
        worker_coord.start_dataforge_extraction.assert_not_called()

    def test_no_op_when_stamp_file_missing(self, tmp_path):
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        forge_dir = tmp_path / "dataforge"
        forge_dir.mkdir()
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_dataforge_cache_dir", return_value=forge_dir),
        ):
            mgr.maybe_prompt_dataforge_refresh()
        worker_coord.start_dataforge_extraction.assert_not_called()

    def test_no_op_when_cache_is_fresh(self, tmp_path):
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        forge_dir = tmp_path / "dataforge"
        forge_dir.mkdir()
        (forge_dir / ".p4k_mtime").write_text("ts", encoding="utf-8")
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_dataforge_cache_dir", return_value=forge_dir),
            patch("src.utils.pak_extractor.dataforge_cache_is_fresh", return_value=True),
        ):
            mgr.maybe_prompt_dataforge_refresh()
        worker_coord.start_dataforge_extraction.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# check_enhancements_freshness — early returns
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckEnhancementsFreshness:
    def test_no_op_when_base_ini_missing(self, tmp_path):
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path):
            mgr.check_enhancements_freshness()
        worker_coord.start_enhancements_pipeline.assert_not_called()

    def test_no_op_when_worker_active(self, tmp_path):
        (tmp_path / "base.ini").write_text("k=v", encoding="utf-8")
        mgr, worker_coord, _ = _make_manager(tmp_path, worker_active=True)
        with patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path):
            mgr.check_enhancements_freshness()
        worker_coord.start_enhancements_pipeline.assert_not_called()

    def test_no_op_when_nothing_missing(self, tmp_path):
        (tmp_path / "base.ini").write_text("k=v", encoding="utf-8")
        enh_file = tmp_path / "ships_desc_enhancements.ini"
        enh_file.write_text("k=v", encoding="utf-8")
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.utils.settings.AppSettings.get_enabled_enhancement_categories",
                return_value={"ship_descs"},
            ),
            patch(
                "src.utils.settings.AppSettings.ENHANCEMENTS_FILES",
                new={"ship_descs": "ships_desc_enhancements.ini"},
            ),
        ):
            mgr.check_enhancements_freshness()
        worker_coord.start_enhancements_pipeline.assert_not_called()

    def test_no_op_when_p4k_missing(self, tmp_path):
        (tmp_path / "base.ini").write_text("k=v", encoding="utf-8")
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.utils.settings.AppSettings.get_enabled_enhancement_categories",
                return_value={"ship_descs"},
            ),
            patch(
                "src.utils.settings.AppSettings.ENHANCEMENTS_FILES",
                new={"ship_descs": "ships_desc_enhancements.ini"},
            ),
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=tmp_path / "missing.p4k"),
        ):
            mgr.check_enhancements_freshness()
        worker_coord.start_enhancements_pipeline.assert_not_called()

    def test_runs_pipeline_when_already_prompted(self, tmp_path):
        (tmp_path / "base.ini").write_text("k=v", encoding="utf-8")
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        mgr, worker_coord, _ = _make_manager(tmp_path)
        mgr.enhancements_prompted = True
        with (
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.utils.settings.AppSettings.get_enabled_enhancement_categories",
                return_value={"ship_descs"},
            ),
            patch(
                "src.utils.settings.AppSettings.ENHANCEMENTS_FILES",
                new={"ship_descs": "ships_desc_enhancements.ini"},
            ),
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
        ):
            mgr.check_enhancements_freshness()
        worker_coord.start_enhancements_pipeline.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# on_startup_sync_finished — delegates
# ─────────────────────────────────────────────────────────────────────────────


class TestOnStartupSyncFinished:
    def test_starts_file_loading_when_p4k_fresh(self, tmp_path):
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch.object(mgr, "check_p4k_freshness", return_value=False),
            patch.object(mgr, "maybe_prompt_dataforge_refresh"),
        ):
            mgr.on_startup_sync_finished()
        assert mgr.check_enhancements_after_loading is True
        worker_coord.start_file_loading.assert_called_once()

    def test_skips_file_loading_when_p4k_extraction_started(self, tmp_path):
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with patch.object(mgr, "check_p4k_freshness", return_value=True):
            mgr.on_startup_sync_finished()
        worker_coord.start_file_loading.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# check_p4k_freshness — dialog paths (QMessageBox patched)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckP4kFreshnessDialogPaths:
    """Tests that reach the QMessageBox prompt by creating conditions where
    base.ini is missing or the p4k file is newer.  QMessageBox is replaced with
    a module-level mock so no Qt event loop is needed."""

    def _setup(self, tmp_path, *, p4k_newer=False):
        """Create tmp_path/Data.p4k; optionally also create base.ini with an older mtime."""
        import os
        import time

        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        if p4k_newer:
            base_ini = tmp_path / "base.ini"
            base_ini.write_text("k=v", encoding="utf-8")
            past = time.time() - 7200
            os.utime(base_ini, (past, past))
        return p4k

    def test_base_missing_user_says_yes_starts_extraction(self, tmp_path):
        p4k = self._setup(tmp_path)
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.gui.startup_flow_manager.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
        ):
            result = mgr.check_p4k_freshness()
        assert result is True
        worker_coord.start_p4k_extraction.assert_called_once()

    def test_base_missing_user_says_no_returns_false(self, tmp_path):
        p4k = self._setup(tmp_path)
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.gui.startup_flow_manager.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No,
            ),
        ):
            result = mgr.check_p4k_freshness()
        assert result is False
        worker_coord.start_p4k_extraction.assert_not_called()

    def test_p4k_newer_user_says_yes_starts_extraction(self, tmp_path):
        p4k = self._setup(tmp_path, p4k_newer=True)
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.gui.startup_flow_manager.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
        ):
            result = mgr.check_p4k_freshness()
        assert result is True
        worker_coord.start_p4k_extraction.assert_called_once()

    def test_p4k_newer_user_says_no_returns_false(self, tmp_path):
        p4k = self._setup(tmp_path, p4k_newer=True)
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.gui.startup_flow_manager.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No,
            ),
        ):
            result = mgr.check_p4k_freshness()
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# maybe_prompt_dataforge_refresh — dialog paths (QMessageBox patched)
# ─────────────────────────────────────────────────────────────────────────────


class TestMaybePromptDataforgeRefreshDialogPaths:
    def _setup(self, tmp_path):
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        forge_dir = tmp_path / "dataforge"
        forge_dir.mkdir()
        (forge_dir / ".p4k_mtime").write_text("ts", encoding="utf-8")
        return p4k, forge_dir

    def test_stale_cache_user_says_yes_starts_extraction(self, tmp_path):
        p4k, forge_dir = self._setup(tmp_path)
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_dataforge_cache_dir", return_value=forge_dir),
            patch("src.utils.pak_extractor.dataforge_cache_is_fresh", return_value=False),
            patch(
                "src.gui.startup_flow_manager.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
        ):
            mgr.maybe_prompt_dataforge_refresh()
        worker_coord.start_dataforge_extraction.assert_called_once()

    def test_stale_cache_user_says_no_does_not_start_extraction(self, tmp_path):
        p4k, forge_dir = self._setup(tmp_path)
        mgr, worker_coord, _ = _make_manager(tmp_path)
        with (
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch("src.utils.settings.AppSettings.get_dataforge_cache_dir", return_value=forge_dir),
            patch("src.utils.pak_extractor.dataforge_cache_is_fresh", return_value=False),
            patch(
                "src.gui.startup_flow_manager.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No,
            ),
        ):
            mgr.maybe_prompt_dataforge_refresh()
        worker_coord.start_dataforge_extraction.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# check_enhancements_freshness — first-prompt path
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckEnhancementsFreshnessFirstPrompt:
    """Tests the code path where enhancements are missing and not yet prompted."""

    def _patches(self, tmp_path, p4k, mgr, *, dialog_return):
        return (
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.utils.settings.AppSettings.get_enabled_enhancement_categories",
                return_value={"ship_descs"},
            ),
            patch(
                "src.utils.settings.AppSettings.ENHANCEMENTS_FILES",
                new={"ship_descs": "ships_desc_enhancements.ini"},
            ),
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch.object(mgr, "_show_enhancement_category_dialog", return_value=dialog_return),
        )

    def test_sets_prompted_flag_before_dialog(self, tmp_path):
        (tmp_path / "base.ini").write_text("k=v", encoding="utf-8")
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        mgr, _, _ = _make_manager(tmp_path)

        with (
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.utils.settings.AppSettings.get_enabled_enhancement_categories",
                return_value={"ship_descs"},
            ),
            patch(
                "src.utils.settings.AppSettings.ENHANCEMENTS_FILES",
                new={"ship_descs": "ships_desc_enhancements.ini"},
            ),
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch.object(mgr, "_show_enhancement_category_dialog", return_value=None),
        ):
            mgr.check_enhancements_freshness()

        assert mgr.enhancements_prompted is True

    def test_starts_pipeline_when_dialog_returns_selections(self, tmp_path):
        (tmp_path / "base.ini").write_text("k=v", encoding="utf-8")
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        mgr, worker_coord, _ = _make_manager(tmp_path)

        with (
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.utils.settings.AppSettings.get_enabled_enhancement_categories",
                return_value={"ship_descs"},
            ),
            patch(
                "src.utils.settings.AppSettings.ENHANCEMENTS_FILES",
                new={"ship_descs": "ships_desc_enhancements.ini"},
            ),
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch.object(mgr, "_show_enhancement_category_dialog", return_value={"ship_descs"}),
        ):
            mgr.check_enhancements_freshness()

        worker_coord.start_enhancements_pipeline.assert_called_once()

    def test_skips_pipeline_when_dialog_returns_none(self, tmp_path):
        (tmp_path / "base.ini").write_text("k=v", encoding="utf-8")
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"pk")
        mgr, worker_coord, _ = _make_manager(tmp_path)

        with (
            patch("src.utils.settings.AppSettings.get_cache_dir", return_value=tmp_path),
            patch(
                "src.utils.settings.AppSettings.get_enabled_enhancement_categories",
                return_value={"ship_descs"},
            ),
            patch(
                "src.utils.settings.AppSettings.ENHANCEMENTS_FILES",
                new={"ship_descs": "ships_desc_enhancements.ini"},
            ),
            patch("src.utils.settings.AppSettings.get_p4k_path", return_value=p4k),
            patch.object(mgr, "_show_enhancement_category_dialog", return_value=None),
        ):
            mgr.check_enhancements_freshness()

        worker_coord.start_enhancements_pipeline.assert_not_called()
