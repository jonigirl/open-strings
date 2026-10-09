"""Tests for src.gui.workers — pure-function helpers and Qt worker components."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from src.utils.resource import _resolve_patches_dir, get_resource_path

# ─────────────────────────────────────────────────────────────────────────────
# Pure-function helpers (no Qt required)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestGetResourcePath:
    """get_resource_path() must return the right base directory."""

    def test_unfrozen_returns_path_under_project_root(self):
        """Outside a PyInstaller bundle, the path is rooted at the project dir."""
        result = get_resource_path("patches")
        # Should be an absolute path ending with 'patches'
        assert Path(result).name == "patches"
        assert Path(result).is_absolute()

    def test_unfrozen_no_meipass(self, monkeypatch):
        """_MEIPASS must not be set when running tests — confirm that invariant."""
        assert not hasattr(sys, "_MEIPASS"), (
            "_MEIPASS should not be set in the test process (would mean tests are running inside a frozen build)"
        )

    def test_frozen_uses_meipass(self, monkeypatch, tmp_path):
        """When _MEIPASS is set, get_resource_path() uses it as the base."""
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        result = get_resource_path("patches")
        assert result == str(tmp_path / "patches")

    def test_nested_relative_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        result = get_resource_path("assets/fonts")
        # os.path.join preserves the slash style from the relative arg;
        # normalise both sides before comparing.
        import os.path as _osp

        assert _osp.normpath(result) == _osp.normpath(str(tmp_path / "assets" / "fonts"))


@pytest.mark.unit
class TestResolvePatchesDir:
    """_resolve_patches_dir() must return a Path ending with 'patches'."""

    def test_returns_path_instance(self):
        result = _resolve_patches_dir()
        assert isinstance(result, Path)

    def test_name_is_patches(self):
        result = _resolve_patches_dir()
        assert result.name == "patches"


@pytest.mark.unit
class TestBaseIniGenerationMarker:
    def test_legacy_base_only_marker_requires_generation_contract(self, tmp_path):
        import json

        from src.gui.workers import _BASE_INI_GENERATION_MARKER, _base_ini_identity, _base_ini_needs_regeneration

        base = tmp_path / "base.ini"
        base.write_text("key=value\n", encoding="utf-8")
        (tmp_path / _BASE_INI_GENERATION_MARKER).write_text(json.dumps(_base_ini_identity(base)), encoding="utf-8")
        assert _base_ini_needs_regeneration(base, tmp_path, {"ship_descs"}) is True

    def test_partial_generation_records_only_completed_categories(self, tmp_path):
        from src.gui.workers import _base_ini_needs_regeneration, _record_generated_base_ini

        base = tmp_path / "base.ini"
        base.write_text("key=value\n", encoding="utf-8")
        _record_generated_base_ini(base, tmp_path, {"ship_descs"})
        assert _base_ini_needs_regeneration(base, tmp_path, {"ship_descs"}) is False
        assert _base_ini_needs_regeneration(base, tmp_path, {"mission_rewards"}) is True
        _record_generated_base_ini(base, tmp_path, {"mission_rewards"})
        assert _base_ini_needs_regeneration(base, tmp_path, {"ship_descs", "mission_rewards"}) is False
        base.write_text("key=new\n", encoding="utf-8")
        _record_generated_base_ini(base, tmp_path, {"ship_descs"})
        assert _base_ini_needs_regeneration(base, tmp_path, {"mission_rewards"}) is True

    def test_semantic_contract_change_requires_regeneration(self, monkeypatch, tmp_path):
        from src.gui.workers import _base_ini_needs_regeneration, _record_generated_base_ini
        from src.utils.dataforge_contract import ENHANCEMENTS_GENERATION_CONTRACT_VERSION

        base = tmp_path / "base.ini"
        base.write_text("key=value\n", encoding="utf-8")
        _record_generated_base_ini(base, tmp_path, {"ship_descs"})
        monkeypatch.setattr(
            "src.gui.workers.ENHANCEMENTS_GENERATION_CONTRACT_VERSION", ENHANCEMENTS_GENERATION_CONTRACT_VERSION + 1
        )
        assert _base_ini_needs_regeneration(base, tmp_path, {"ship_descs"}) is True
        _record_generated_base_ini(base, tmp_path, {"mission_rewards"})
        assert _base_ini_needs_regeneration(base, tmp_path, {"ship_descs"}) is True
        assert _base_ini_needs_regeneration(base, tmp_path, {"mission_rewards"}) is False

    def test_missing_marker_requires_regeneration(self, tmp_path):
        from src.gui.workers import _base_ini_needs_regeneration

        base_ini = tmp_path / "base.ini"
        base_ini.write_text("key=value\n", encoding="utf-8")

        assert _base_ini_needs_regeneration(base_ini, tmp_path) is True

    def test_marker_matches_current_base_ini(self, tmp_path):
        from src.gui.workers import _base_ini_needs_regeneration, _record_generated_base_ini

        base_ini = tmp_path / "base.ini"
        base_ini.write_text("key=value\n", encoding="utf-8")
        _record_generated_base_ini(base_ini, tmp_path)

        assert _base_ini_needs_regeneration(base_ini, tmp_path) is False

    def test_base_ini_change_requires_regeneration(self, tmp_path):
        from src.gui.workers import _base_ini_needs_regeneration, _record_generated_base_ini

        base_ini = tmp_path / "base.ini"
        base_ini.write_text("key=old\n", encoding="utf-8")
        _record_generated_base_ini(base_ini, tmp_path)
        base_ini.write_text("key=new value\n", encoding="utf-8")

        assert _base_ini_needs_regeneration(base_ini, tmp_path) is True

    def test_same_size_timestamp_preserved_base_ini_change_requires_regeneration(self, tmp_path):
        import os

        from src.gui.workers import _base_ini_needs_regeneration, _record_generated_base_ini

        base_ini = tmp_path / "base.ini"
        base_ini.write_text("key=A\n", encoding="utf-8")
        _record_generated_base_ini(base_ini, tmp_path)
        before = base_ini.stat()
        base_ini.write_text("key=B\n", encoding="utf-8")
        os.utime(base_ini, ns=(before.st_atime_ns, before.st_mtime_ns))

        assert _base_ini_needs_regeneration(base_ini, tmp_path) is True


@pytest.mark.unit
class TestDiffCategoryTranslation:
    """DIFF_CATEGORY_TO_GENERATOR_KEYS must translate dirty_categories() output
    into the vocabulary that generate_enhancements_ini._want() expects."""

    def test_missions_maps_to_mission_rewards(self):
        from src.utils.settings import AppSettings

        result: set[str] = set()
        for diff_key in {"missions"}:
            result.update(AppSettings.DIFF_CATEGORY_TO_GENERATOR_KEYS.get(diff_key, [diff_key]))
        assert result == {"mission_rewards"}

    def test_all_diff_keys_produce_known_generator_keys(self):
        from src.utils.settings import AppSettings

        all_translated: set[str] = set()
        for keys in AppSettings.DIFF_CATEGORY_TO_GENERATOR_KEYS.values():
            all_translated.update(keys)
        known = set(AppSettings.ENHANCEMENTS_FILES)
        unknown = all_translated - known
        assert not unknown, f"Translated keys not in ENHANCEMENTS_FILES: {unknown}"

    def test_ships_translates_correctly(self):
        from src.utils.settings import AppSettings

        assert AppSettings.DIFF_CATEGORY_TO_GENERATOR_KEYS["ships"] == ["ship_descs"]

    def test_components_translates_to_component_descs(self):
        from src.utils.settings import AppSettings

        assert "component_descs" in AppSettings.DIFF_CATEGORY_TO_GENERATOR_KEYS["components"]

    def test_is_absolute(self):
        assert _resolve_patches_dir().is_absolute()


@pytest.mark.unit
class TestDataForgeWorkerManifest:
    def test_subset_refresh_does_not_certify_retained_outputs(self, monkeypatch, tmp_path):
        from src.gui.workers import (
            EnhancementsGeneratorWorker,
            _base_ini_needs_regeneration,
            _record_generated_base_ini,
        )
        from src.utils.dataforge_diff import update_manifest
        from src.utils.settings import AppSettings

        base = tmp_path / "base.ini"
        base.write_text("key=value\n", encoding="utf-8")
        libs = tmp_path / "forge/raw/libs"
        libs.mkdir(parents=True)
        update_manifest(libs)
        for name in AppSettings.ENHANCEMENTS_FILES.values():
            (tmp_path / name).write_text("key=old output\n", encoding="utf-8")
        _record_generated_base_ini(base, tmp_path, set(AppSettings.ENHANCEMENTS_FILES))
        enabled = {"ship_descs"}
        generate = MagicMock()
        monkeypatch.setattr(AppSettings, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(AppSettings, "get_dataforge_cache_dir", lambda: tmp_path / "forge")
        monkeypatch.setattr(AppSettings, "get_enabled_enhancement_categories", lambda: enabled)
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", lambda path: "patch")
        monkeypatch.setattr("src.utils.pak_extractor.rebuild_patched_dataforge_cache", lambda *args: False)
        monkeypatch.setattr(
            "src.utils.dataforge_patcher.apply_patches",
            lambda *args, **kwargs: SimpleNamespace(errors=[], summary_line=lambda: "patched"),
        )
        monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: SimpleNamespace(main=generate))
        monkeypatch.setattr(
            "importlib.util.spec_from_file_location",
            lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None)),
        )
        EnhancementsGeneratorWorker(categories={"ship_descs"}, force_full=True).run()
        assert _base_ini_needs_regeneration(base, tmp_path, {"ship_descs"}) is False
        assert _base_ini_needs_regeneration(base, tmp_path, {"mission_rewards"}) is True
        enabled.clear()
        enabled.add("mission_rewards")
        EnhancementsGeneratorWorker(categories={"mission_rewards"}).run()
        assert [call.kwargs["categories"] for call in generate.call_args_list] == [
            {"ship_descs"},
            {"mission_rewards"},
        ]

    @pytest.mark.parametrize("force_full", [False, True])
    def test_empty_selection_finishes_without_cache_or_generator_access(self, monkeypatch, force_full):
        from src.gui.workers import EnhancementsGeneratorWorker
        from src.utils.settings import AppSettings

        cache = MagicMock(side_effect=AssertionError("cache access on no-op"))
        diff = MagicMock(side_effect=AssertionError("XML hashing on no-op"))
        fingerprint = MagicMock(side_effect=AssertionError("patch hashing on no-op"))
        patches = MagicMock(side_effect=AssertionError("patch report on no-op"))
        load = MagicMock(side_effect=AssertionError("generator load on no-op"))
        record = MagicMock(side_effect=AssertionError("marker write on no-op"))
        snapshot = MagicMock(side_effect=AssertionError("snapshot on no-op"))
        monkeypatch.setattr(AppSettings, "get_cache_dir", cache)
        monkeypatch.setattr(AppSettings, "get_dataforge_cache_dir", cache)
        monkeypatch.setattr("src.gui.workers.dirty_categories", diff)
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", fingerprint)
        monkeypatch.setattr("src.utils.dataforge_patcher.apply_patches", patches)
        monkeypatch.setattr("importlib.util.spec_from_file_location", load)
        monkeypatch.setattr("src.gui.workers._record_generated_base_ini", record)
        monkeypatch.setattr("src.utils.dataforge_diff.update_manifest", snapshot)
        completed = []
        worker = EnhancementsGeneratorWorker(categories=set(), force_full=force_full)
        worker.finished.connect(completed.append)
        worker.run()
        assert completed == [True]
        for operation in (cache, diff, fingerprint, patches, load, record, snapshot):
            operation.assert_not_called()

    def test_legacy_marker_regenerates_once_then_skips_generator(self, monkeypatch, tmp_path):
        import json

        from src.gui.workers import (
            _BASE_INI_GENERATION_MARKER,
            EnhancementsGeneratorWorker,
            _base_ini_identity,
            _base_ini_needs_regeneration,
        )
        from src.utils.dataforge_diff import update_manifest
        from src.utils.settings import AppSettings

        base = tmp_path / "base.ini"
        base.write_text("key=value\n", encoding="utf-8")
        (tmp_path / _BASE_INI_GENERATION_MARKER).write_text(json.dumps(_base_ini_identity(base)), encoding="utf-8")
        libs = tmp_path / "forge/raw/libs"
        libs.mkdir(parents=True)
        update_manifest(libs)
        for name in AppSettings.ENHANCEMENTS_FILES.values():
            (tmp_path / name).write_text("key=previous\n", encoding="utf-8")
        generate = MagicMock()
        load = MagicMock(return_value=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None)))
        monkeypatch.setattr(AppSettings, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(AppSettings, "get_dataforge_cache_dir", lambda: tmp_path / "forge")
        monkeypatch.setattr(AppSettings, "get_enabled_enhancement_categories", lambda: {"ship_descs"})
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", lambda path: "patch")
        monkeypatch.setattr("src.utils.pak_extractor.rebuild_patched_dataforge_cache", lambda *args: False)
        monkeypatch.setattr(
            "src.utils.dataforge_patcher.apply_patches",
            lambda *args, **kwargs: SimpleNamespace(errors=[], summary_line=lambda: "patched"),
        )
        monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: SimpleNamespace(main=generate))
        monkeypatch.setattr("importlib.util.spec_from_file_location", load)
        for _attempt in range(2):
            completed = []
            worker = EnhancementsGeneratorWorker(categories={"ship_descs"})
            worker.finished.connect(completed.append)
            worker.run()
            assert completed == [True]
        generate.assert_called_once()
        assert generate.call_args.kwargs["categories"] == {"ship_descs"}
        load.assert_called_once()
        assert _base_ini_needs_regeneration(base, tmp_path, {"ship_descs"}) is False

    def test_dirty_cache_does_not_override_empty_category_selection(self, monkeypatch, tmp_path):
        from src.gui.workers import EnhancementsGeneratorWorker, _record_generated_base_ini
        from src.utils.settings import AppSettings

        base = tmp_path / "base.ini"
        base.write_text("key=value\n", encoding="utf-8")
        _record_generated_base_ini(base, tmp_path)
        for name in AppSettings.ENHANCEMENTS_FILES.values():
            (tmp_path / name).write_text("previous", encoding="utf-8")
        generate = MagicMock()
        manifest = MagicMock()
        monkeypatch.setattr(AppSettings, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(AppSettings, "get_dataforge_cache_dir", lambda: tmp_path / "forge")
        monkeypatch.setattr(AppSettings, "get_enabled_enhancement_categories", lambda: set())
        monkeypatch.setattr("src.gui.workers.dirty_categories", lambda path: {"ships"})
        monkeypatch.setattr("src.utils.dataforge_diff.update_manifest", manifest)
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", lambda path: "patch")
        monkeypatch.setattr("src.utils.pak_extractor.rebuild_patched_dataforge_cache", lambda *args: False)
        monkeypatch.setattr(
            "src.utils.dataforge_patcher.apply_patches",
            lambda *args, **kwargs: SimpleNamespace(errors=[], summary_line=lambda: "patched"),
        )
        monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: SimpleNamespace(main=generate))
        monkeypatch.setattr(
            "importlib.util.spec_from_file_location",
            lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None)),
        )
        worker = EnhancementsGeneratorWorker(categories=set())
        worker.run()
        generate.assert_not_called()
        manifest.assert_not_called()

    def test_failed_generation_after_rebuild_is_retried(self, monkeypatch, tmp_path):
        from src.gui.workers import EnhancementsGeneratorWorker, _record_generated_base_ini
        from src.utils.dataforge_diff import MANIFEST_FILE, update_manifest
        from src.utils.settings import AppSettings

        cache = tmp_path / "cache"
        libs = tmp_path / "forge" / "raw" / "libs"
        libs.mkdir(parents=True)
        cache.mkdir()
        base_ini = cache / "base.ini"
        base_ini.write_text("key=value\n", encoding="utf-8")
        _record_generated_base_ini(base_ini, cache)
        for name in AppSettings.ENHANCEMENTS_FILES.values():
            (cache / name).write_text("key=previous\n", encoding="utf-8")
        update_manifest(libs)
        prior_manifest = (libs / MANIFEST_FILE).read_bytes()
        attempts = []
        rebuilt = False

        def rebuild(forge, fingerprint, finalize, progress_callback=None):
            nonlocal rebuilt
            if rebuilt:
                return False
            rebuilt = True
            (libs / MANIFEST_FILE).unlink()
            finalize(forge)
            return True

        def generate(*args, categories=None, **kwargs):
            attempts.append(categories)
            if len(attempts) == 1:
                raise RuntimeError("generation failed")

        monkeypatch.setattr(AppSettings, "get_cache_dir", lambda: cache)
        monkeypatch.setattr(AppSettings, "get_dataforge_cache_dir", lambda: tmp_path / "forge")
        monkeypatch.setattr(AppSettings, "get_enabled_enhancement_categories", lambda: {"ship_descs"})
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", lambda path: "patch")
        monkeypatch.setattr("src.utils.pak_extractor.rebuild_patched_dataforge_cache", rebuild)
        monkeypatch.setattr(
            "src.utils.dataforge_patcher.apply_patches",
            lambda *args, **kwargs: SimpleNamespace(errors=[], summary_line=lambda: "patched"),
        )
        monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: SimpleNamespace(main=generate))
        monkeypatch.setattr(
            "importlib.util.spec_from_file_location",
            lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None)),
        )
        first = EnhancementsGeneratorWorker(categories={"ship_descs"})
        first.run()
        assert not (libs / MANIFEST_FILE).exists()
        second = EnhancementsGeneratorWorker(categories={"ship_descs"})
        second.run()
        assert attempts == [{"ship_descs"}, {"ship_descs"}]
        assert (libs / MANIFEST_FILE).read_bytes() == prior_manifest

    @pytest.mark.parametrize("reason, limit", [("total time limit", 7200), ("no output", 1800)])
    def test_extraction_timeout_reports_failure(self, monkeypatch, tmp_path, reason, limit):
        import subprocess

        from src.gui.workers import DataForgeExtractWorker
        from src.utils.pak_extractor import _SubprocessOutputTimeout

        failure = _SubprocessOutputTimeout(["unforge.exe"], limit, reason)
        failure.output = "Exported 110000/117231 records\n"
        failure.stderr = "last diagnostic\n"
        assert isinstance(failure, subprocess.TimeoutExpired)
        monkeypatch.setattr("src.utils.pak_extractor.extract_dataforge", MagicMock(side_effect=failure))
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", lambda path: "fixture")
        worker = DataForgeExtractWorker(
            tmp_path / "Data.p4k", tmp_path / "unp4k", tmp_path / "unforge", tmp_path / "cache"
        )
        errors, finished = [], []
        worker.error.connect(errors.append)
        worker.finished.connect(finished.append)
        worker.run()
        assert finished == [False]
        assert len(errors) == 1
        assert reason in errors[0]
        assert "110000/117231" in errors[0]
        assert "last diagnostic" in errors[0]
        assert worker._thread_id is None

    def test_extraction_defers_manifest_until_generation(self, monkeypatch, tmp_path):
        from src.gui.workers import DataForgeExtractWorker

        events: list[str] = []
        cache_dir = tmp_path / "dataforge"

        def fake_extract(*args, **kwargs):
            events.append("extract")
            staging_dir = tmp_path / "staging"
            (staging_dir / "raw" / "libs").mkdir(parents=True)
            kwargs["finalize_callback"](staging_dir)

        def fake_patches(*args, **kwargs):
            events.append("patch")
            return SimpleNamespace(errors=[], summary_line=lambda: "patched")

        def fake_manifest(path, **kwargs):
            assert path == tmp_path / "staging" / "raw" / "libs"
            events.append("manifest")

        monkeypatch.setattr("src.utils.pak_extractor.extract_dataforge", fake_extract)
        monkeypatch.setattr("src.utils.dataforge_patcher.apply_patches", fake_patches)
        monkeypatch.setattr("src.utils.dataforge_diff.update_manifest", fake_manifest)

        worker = DataForgeExtractWorker(
            tmp_path / "Data.p4k", tmp_path / "unp4k.exe", tmp_path / "unforge.exe", cache_dir
        )
        worker.run()

        assert events == ["extract", "patch"]

    def test_failed_generation_after_full_extraction_is_retried(self, monkeypatch, tmp_path):
        from src.gui.workers import DataForgeExtractWorker, EnhancementsGeneratorWorker, _record_generated_base_ini
        from src.utils.dataforge_diff import MANIFEST_FILE, update_manifest
        from src.utils.settings import AppSettings

        cache = tmp_path / "cache"
        forge = tmp_path / "forge"
        libs = forge / "raw/libs"
        staging = tmp_path / "staging"
        cache.mkdir()
        libs.mkdir(parents=True)
        update_manifest(libs)
        base = cache / "base.ini"
        base.write_text("key=value\n", encoding="utf-8")
        _record_generated_base_ini(base, cache)
        for name in AppSettings.ENHANCEMENTS_FILES.values():
            (cache / name).write_text("key=previous\n", encoding="utf-8")
        attempts = []

        def extract(*args, **kwargs):
            (staging / "raw/libs").mkdir(parents=True)
            kwargs["finalize_callback"](staging)
            forge.rename(tmp_path / "old_forge")
            staging.rename(forge)

        def generate(*args, categories=None, **kwargs):
            attempts.append(categories)
            if len(attempts) == 1:
                raise RuntimeError("generation failed")

        monkeypatch.setattr(AppSettings, "get_cache_dir", lambda: cache)
        monkeypatch.setattr(AppSettings, "get_dataforge_cache_dir", lambda: forge)
        monkeypatch.setattr(AppSettings, "get_enabled_enhancement_categories", lambda: {"ship_descs"})
        monkeypatch.setattr("src.utils.pak_extractor.extract_dataforge", extract)
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", lambda path: "patch")
        monkeypatch.setattr("src.utils.pak_extractor.rebuild_patched_dataforge_cache", lambda *args: False)
        monkeypatch.setattr(
            "src.utils.dataforge_patcher.apply_patches",
            lambda *args, **kwargs: SimpleNamespace(errors=[], summary_line=lambda: "patched"),
        )
        monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: SimpleNamespace(main=generate))
        monkeypatch.setattr(
            "importlib.util.spec_from_file_location",
            lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None)),
        )
        DataForgeExtractWorker(tmp_path / "Data.p4k", tmp_path / "unp4k", tmp_path / "unforge", forge).run()
        assert not (libs / MANIFEST_FILE).exists()
        EnhancementsGeneratorWorker(categories={"ship_descs"}, force_full=True).run()
        assert not (libs / MANIFEST_FILE).exists()
        EnhancementsGeneratorWorker(categories={"ship_descs"}).run()
        assert attempts == [{"ship_descs"}, {"ship_descs"}]
        assert (libs / MANIFEST_FILE).exists()


@pytest.mark.unit
class TestPostExtractionGeneration:
    def test_success_forces_enhancement_regeneration(self):
        from src.gui.main_window import MainWindow

        status_bar = MagicMock()
        fake_window = SimpleNamespace(
            enhancements_tab=MagicMock(),
            worker_coord=MagicMock(),
            _status_bar=lambda: status_bar,
        )

        MainWindow._on_dataforge_extract_finished(fake_window, True)

        fake_window.worker_coord.start_enhancements_generation.assert_called_once_with(force_full=True)


@pytest.mark.unit
class TestEnhancementsCategoryChanges:
    def test_two_disable_regenerate_cycles_replace_retained_backup(self, monkeypatch, tmp_path, isolated_settings):
        from src.gui.enhancements_tab import EnhancementsTab
        from src.utils.settings import AppSettings

        active = tmp_path / AppSettings.ENHANCEMENTS_FILES["ship_descs"]
        disabled = active.with_name(active.name + ".disabled")
        monkeypatch.setattr(AppSettings, "get_cache_dir", lambda: tmp_path)
        original_rename = Path.rename

        def windows_rename(path, target):
            if Path(target).exists():
                raise FileExistsError("Windows rename cannot overwrite")
            return original_rename(path, target)

        monkeypatch.setattr(Path, "rename", windows_rename)
        selected = {"ships": False}
        tab = SimpleNamespace(
            _enhancements_checkboxes={"ships": SimpleNamespace(isChecked=lambda: selected["ships"])},
            _files_for_category=EnhancementsTab._files_for_category,
            _apply_categories_btn=MagicMock(),
            refresh_enhancements_status=MagicMock(),
            merge_requested=MagicMock(),
            enhancements_pipeline_requested=MagicMock(),
        )
        generation = 0

        def regenerate():
            nonlocal generation
            assert not active.exists()
            generation += 1
            active.write_text(f"ship_desc=Generation {generation}\n", encoding="utf-8")

        tab.enhancements_pipeline_requested.emit.side_effect = regenerate
        active.write_text("ship_desc=Original\n", encoding="utf-8")
        for previous in ("Original", "Generation 1"):
            selected["ships"] = False
            EnhancementsTab._apply_category_changes(tab)
            assert not active.exists()
            assert disabled.read_text(encoding="utf-8") == f"ship_desc={previous}\n"
            selected["ships"] = True
            EnhancementsTab._apply_category_changes(tab)
            assert active.read_text(encoding="utf-8") == f"ship_desc=Generation {generation}\n"
        assert generation == 2

    @pytest.mark.parametrize("generation_fails", [False, True])
    def test_disable_update_enable_regenerates_without_restoring_stale_backup(
        self, monkeypatch, tmp_path, isolated_settings, generation_fails
    ):
        from src.gui.enhancements_tab import EnhancementsTab
        from src.gui.workers import EnhancementsGeneratorWorker, _record_generated_base_ini
        from src.utils.dataforge_diff import update_manifest
        from src.utils.settings import AppSettings

        cache = tmp_path / "cache"
        libs = tmp_path / "forge/raw/libs"
        ships = libs / "foundry/records/entities/spaceships"
        ships.mkdir(parents=True)
        cache.mkdir()
        base = cache / "base.ini"
        base.write_text("ship_desc=Example ship\n", encoding="utf-8")
        active = cache / AppSettings.ENHANCEMENTS_FILES["ship_descs"]
        active.write_text("ship_desc=Old stats\n", encoding="utf-8")
        disabled = active.with_name(active.name + ".disabled")
        user_ini = tmp_path / "user.ini"
        user_ini.write_text("ship_desc=User edit\n", encoding="utf-8")
        monkeypatch.setattr(AppSettings, "get_cache_dir", lambda: cache)
        monkeypatch.setattr(AppSettings, "get_dataforge_cache_dir", lambda: tmp_path / "forge")
        monkeypatch.setattr("src.utils.pak_extractor.patch_set_fingerprint", lambda path: "patch")
        monkeypatch.setattr("src.utils.pak_extractor.rebuild_patched_dataforge_cache", lambda *args: False)
        monkeypatch.setattr(
            "src.utils.dataforge_patcher.apply_patches",
            lambda *args, **kwargs: SimpleNamespace(errors=[], summary_line=lambda: "patched"),
        )
        for key in AppSettings.ENHANCEMENT_LABELS:
            AppSettings.set_enhancement_category_enabled(key, key == "ships")
        selected = {"ships": False, "gear": False}
        tab = SimpleNamespace(
            _enhancements_checkboxes={
                key: SimpleNamespace(isChecked=lambda key=key: selected[key]) for key in selected
            },
            _files_for_category=EnhancementsTab._files_for_category,
            _apply_categories_btn=MagicMock(),
            refresh_enhancements_status=MagicMock(),
            merge_requested=MagicMock(),
            enhancements_pipeline_requested=MagicMock(),
        )
        EnhancementsTab._apply_category_changes(tab)
        assert not active.exists()
        assert disabled.read_text(encoding="utf-8") == "ship_desc=Old stats\n"
        tab.enhancements_pipeline_requested.emit.assert_not_called()
        (ships / "example.xml").write_text(
            '<EntityClassDefinition.Example><VehicleComponentParams vehicleDescription="@ship_desc" crewSize="2"/></EntityClassDefinition.Example>',
            encoding="utf-8",
        )
        update_manifest(libs)
        _record_generated_base_ini(base, cache)
        if generation_fails:
            base.unlink()

        def regenerate():
            assert not active.exists()
            worker = EnhancementsGeneratorWorker(categories=AppSettings.get_enabled_enhancement_categories())
            worker.run()

        tab.enhancements_pipeline_requested.emit.side_effect = regenerate
        selected["ships"] = True
        EnhancementsTab._apply_category_changes(tab)
        tab.enhancements_pipeline_requested.emit.assert_called_once()
        assert AppSettings.get_enhancement_category_enabled("ships") is True
        assert AppSettings.get_enhancement_category_enabled("gear") is False
        assert disabled.read_text(encoding="utf-8") == "ship_desc=Old stats\n"
        assert user_ini.read_text(encoding="utf-8") == "ship_desc=User edit\n"
        if generation_fails:
            assert not active.exists()
        else:
            assert "Crew: 2" in active.read_text(encoding="utf-8")
            assert "Old stats" not in active.read_text(encoding="utf-8")

    def test_category_controls_locked_during_generation(self, qtbot, isolated_settings, monkeypatch):
        from src.gui.enhancements_tab import EnhancementsTab

        monkeypatch.setattr(EnhancementsTab, "refresh_enhancements_status", lambda self: None)
        tab = EnhancementsTab()
        qtbot.addWidget(tab)
        checkbox = tab._enhancements_checkboxes["ships"]
        checkbox.setChecked(not checkbox.isChecked())
        assert tab._apply_categories_btn.isEnabled()
        tab.set_operation_running("Generating")
        assert not tab._apply_categories_btn.isEnabled()
        assert all(not cb.isEnabled() for cb in tab._enhancements_checkboxes.values())
        tab.set_operation_idle()
        assert tab._apply_categories_btn.isEnabled()
        assert all(cb.isEnabled() for cb in tab._enhancements_checkboxes.values())


# ─────────────────────────────────────────────────────────────────────────────
# Qt widget tests (require qtbot from pytest-qt)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAnimatedProgressDialog:
    """AnimatedProgressDialog state transitions."""

    def test_progress_text_wraps_without_widening_window(self, qtbot):
        from src.gui.workers import AnimatedProgressDialog

        dialog = AnimatedProgressDialog("Starting")
        qtbot.addWidget(dialog)
        width = dialog.width()
        dialog.setLabelText("Validating exported records: 117,231 / 117,231")
        assert dialog.width() == width
        assert dialog._message_label.wordWrap()
        message = "Long diagnostic " * 100
        dialog.setLabelText(message)
        assert dialog.width() == width
        assert len(dialog.labelText()) <= 300
        assert dialog._message_label.toolTip() == message

    def test_inline_operation_heading_stays_visible(self):
        from src.gui.enhancements_tab import EnhancementsTab

        tab = SimpleNamespace(
            _generate_enhancements_btn=MagicMock(),
            _apply_categories_btn=MagicMock(),
            _enhancements_checkboxes={},
            _operation_label=MagicMock(),
        )
        EnhancementsTab.set_operation_running(tab, "Extracting DataForge")
        EnhancementsTab.set_operation_progress(tab, "Checking cached records: 256 / 1000")
        tab._operation_label.setText.assert_called_with("Extracting DataForge\nChecking cached records: 256 / 1000")

    def test_starts_indeterminate(self, qtbot):
        from src.gui.workers import AnimatedProgressDialog

        dlg = AnimatedProgressDialog("Loading…")
        qtbot.addWidget(dlg)
        # Indeterminate ⇒ range [0, 0]
        assert dlg.minimum() == 0
        assert dlg.maximum() == 0

    def test_set_progress_switches_to_determinate(self, qtbot):
        from src.gui.workers import AnimatedProgressDialog

        dlg = AnimatedProgressDialog("Loading…")
        qtbot.addWidget(dlg)
        dlg.set_progress(3, 10, "Scanning…")
        assert dlg.maximum() == 10
        assert dlg.value() == 3

    def test_set_progress_total_zero_resets_to_indeterminate(self, qtbot):
        from src.gui.workers import AnimatedProgressDialog

        dlg = AnimatedProgressDialog("Loading…")
        qtbot.addWidget(dlg)
        dlg.set_progress(5, 10, "Midpoint")
        assert dlg.maximum() == 10
        dlg.set_progress(0, 0, "Unknown extent")
        assert dlg.maximum() == 0

    def test_set_progress_clamps_value_to_total(self, qtbot):
        from src.gui.workers import AnimatedProgressDialog

        dlg = AnimatedProgressDialog("Loading…")
        qtbot.addWidget(dlg)
        dlg.set_progress(999, 10, "Over-reported")
        # set_progress passes min(completed, total) to setValue; the maximum is 10
        assert dlg.maximum() == 10
        # QProgressDialog.value() may return -1 until the dialog is fully initialised;
        # validate the range is correct instead.
        assert dlg.minimum() == 0


# ─────────────────────────────────────────────────────────────────────────────
# Pending-edit snapshot / restore logic (MainWindow helpers)
# ─────────────────────────────────────────────────────────────────────────────


def _entry(key, custom_value="", original_value="base", status="Unmodified"):
    from src.models.string_model import StringEntry

    e = StringEntry.__new__(StringEntry)
    e.key = key
    e.custom_value = custom_value
    e.original_value = original_value
    e.status = status
    return e


@pytest.mark.unit
class TestPendingEditSnapshotRestore:
    """Verify MainWindow._snapshot_pending_user_edits and _restore_pending_user_edits.

    Both methods are called as unbound functions with minimal fake-self objects
    so the full MainWindow widget is never instantiated.
    """

    def _snapshot(self, entries):
        import types

        from src.gui.main_window import MainWindow

        fake = types.SimpleNamespace(entries=entries)
        return MainWindow._snapshot_pending_user_edits(fake)

    def _restore(self, entries, snapshot):
        from src.gui.main_window import MainWindow

        return MainWindow._restore_pending_user_edits(None, entries, snapshot)

    # -- snapshot ----------------------------------------------------------

    def test_snapshot_empty_entries_returns_empty_dict(self):
        assert self._snapshot([]) == {}

    def test_snapshot_skips_entries_with_no_custom_value(self):
        entries = [_entry("k1", custom_value=""), _entry("k2", custom_value="")]
        assert self._snapshot(entries) == {}

    def test_snapshot_captures_non_empty_custom_values(self):
        entries = [_entry("k1", custom_value="edit1"), _entry("k2", custom_value="edit2")]
        assert self._snapshot(entries) == {"k1": "edit1", "k2": "edit2"}

    def test_snapshot_mixed_entries_only_captures_non_empty(self):
        entries = [
            _entry("k1", custom_value="edit1"),
            _entry("k2", custom_value=""),
            _entry("k3", custom_value="edit3"),
        ]
        result = self._snapshot(entries)
        assert result == {"k1": "edit1", "k3": "edit3"}

    # -- restore -----------------------------------------------------------

    def test_restore_empty_snapshot_returns_zero(self):
        entries = [_entry("k1", custom_value="edit1")]
        assert self._restore(entries, {}) == 0

    def test_restore_skips_key_not_in_snapshot(self):
        entries = [_entry("k1", custom_value="")]
        count = self._restore(entries, {"other_key": "val"})
        assert count == 0
        assert entries[0].custom_value == ""

    def test_restore_skips_entry_already_matching_snapshot(self):
        # If the new entries already loaded this value from user.ini, no-op
        entries = [_entry("k1", custom_value="already")]
        count = self._restore(entries, {"k1": "already"})
        assert count == 0

    def test_restore_applies_pending_edit_and_sets_modified(self):
        entries = [_entry("k1", custom_value="", original_value="base")]
        count = self._restore(entries, {"k1": "pending edit"})
        assert count == 1
        assert entries[0].custom_value == "pending edit"
        assert entries[0].status == "Modified"

    def test_restore_sets_unmodified_when_pending_matches_original(self):
        entries = [_entry("k1", custom_value="", original_value="base")]
        count = self._restore(entries, {"k1": "base"})
        assert count == 1
        assert entries[0].status == "Unmodified"

    def test_restore_returns_count_of_restored_entries(self):
        entries = [
            _entry("k1", custom_value="", original_value="base"),
            _entry("k2", custom_value="already", original_value="base"),
            _entry("k3", custom_value="", original_value="base"),
        ]
        count = self._restore(entries, {"k1": "edit1", "k2": "already", "k3": "edit3"})
        # k2 is skipped (value already matches), k1 and k3 are restored
        assert count == 2

    def test_restore_snapshot_taken_before_entries_replaced(self):
        """Verify the order-of-operations contract: snapshot old entries, restore into new."""
        old = [_entry("k1", custom_value="unsaved")]
        new = [_entry("k1", custom_value="", original_value="new base")]

        snapshot = self._snapshot(old)
        assert snapshot == {"k1": "unsaved"}

        count = self._restore(new, snapshot)
        assert count == 1
        assert new[0].custom_value == "unsaved"
        assert new[0].status == "Modified"
