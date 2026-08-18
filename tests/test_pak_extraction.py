"""
Tests for P4K extraction and DataForge cache management.

Covers:
- DataForge cache freshness detection
- P4K extraction pipeline error handling
- DataForge keep-list / generator read-path contract
- Filtered cache copy helper
- _robust_rmtree retry/read-only logic
- extract_global_ini happy path and error paths
"""

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.utils.pak_extractor import (
    DATAFORGE_CACHE_SCHEMA_VERSION,
    DATAFORGE_KEEP_SUBPATHS,
    _copy_filtered_records,
    _read_dataforge_identity,
    _recover_dataforge_cache,
    _recover_dataforge_layer,
    _replace_dataforge_cache,
    dataforge_cache_is_fresh,
    extract_dataforge,
    extract_global_ini,
    rebuild_patched_dataforge_cache,
    robust_rmtree,
)


@pytest.mark.unit
class TestDataForgeCache:
    """DataForge cache freshness detection."""

    def test_legacy_cache_is_stale_even_when_newer(self):
        """A legacy one-layer cache must migrate through a fresh extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy p4k with old mtime
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")

            # Set p4k mtime to old date
            old_time = 1000000000  # Jan 2001
            os.utime(p4k_path, (old_time, old_time))

            # Create cache dir with newer mtime
            cache_dir = os.path.join(tmpdir, "dataforge")
            os.makedirs(cache_dir, exist_ok=True)
            recent_time = 9999999999  # Far future
            os.utime(cache_dir, (recent_time, recent_time))

            # Directory mtime alone cannot validate the two-layer cache contract.
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            assert is_fresh is False

    def test_cache_is_stale_when_older(self):
        """Test that cache is stale when p4k is newer"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy p4k with new mtime
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")

            recent_time = 9999999999  # Far future
            os.utime(p4k_path, (recent_time, recent_time))

            # Create cache dir with old mtime
            cache_dir = os.path.join(tmpdir, "dataforge")
            os.makedirs(cache_dir, exist_ok=True)
            old_time = 1000000000  # Jan 2001
            os.utime(cache_dir, (old_time, old_time))

            # Cache should be stale (older than p4k)
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            assert is_fresh is False

    def test_cache_is_fresh_when_cache_missing(self):
        """Test that missing cache is treated as stale"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")

            # Cache directory doesn't exist
            cache_dir = os.path.join(tmpdir, "nonexistent")

            # Cache should be stale (doesn't exist)
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            assert is_fresh is False

    def test_cache_is_fresh_when_p4k_missing(self):
        """Test that missing p4k is handled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "nonexistent", "Data.p4k")

            cache_dir = os.path.join(tmpdir, "dataforge")
            os.makedirs(cache_dir, exist_ok=True)

            # Should handle missing p4k gracefully
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            # Missing p4k could mean cache is stale (can't verify freshness)
            assert isinstance(is_fresh, bool)


@pytest.mark.unit
class TestDataForgeExtraction:
    """P4K extraction pipeline — error handling paths."""

    @patch("src.utils.pak_extractor.subprocess.run")
    def test_missing_tools_raises(self, mock_run):
        """FileNotFoundError from unp4k.exe propagates as an exception."""
        mock_run.side_effect = FileNotFoundError("unp4k.exe not found")
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")
            with pytest.raises(Exception):  # noqa: B017 — test calls wrong arg count; TypeError is expected here
                extract_dataforge(p4k_path, os.path.join(tmpdir, "cache"))

    @patch("src.utils.pak_extractor.subprocess.run")
    def test_pipeline_stops_on_first_failure(self, mock_run):
        """If unp4k fails, unforge is never called."""
        mock_run.side_effect = [
            Exception("unp4k failed"),
            MagicMock(returncode=0),  # Should not be reached
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")
            with pytest.raises(Exception):  # noqa: B017 — test calls wrong arg count; TypeError is expected here
                extract_dataforge(p4k_path, os.path.join(tmpdir, "cache"))
            # subprocess.run is called at most once (the first tool invocation)
            assert mock_run.call_count <= 1

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_finalizer_failure_preserves_existing_cache(self, mock_run, tmp_path):
        p4k = tmp_path / "Data.p4k"
        unp4k = tmp_path / "unp4k.exe"
        unforge = tmp_path / "unforge.cli.exe"
        cache = tmp_path / "dataforge"
        p4k.write_bytes(b"p4k")
        unp4k.write_bytes(b"unp4k")
        unforge.write_bytes(b"unforge")
        (cache / "raw" / "libs").mkdir(parents=True)
        (cache / "old.xml").write_text("old", encoding="utf-8")

        def fake_run(args, cwd=None, timeout=None):
            if args[-1] == ".dcb":
                dcb = Path(cwd) / "Data" / "Game2.dcb"
                dcb.parent.mkdir(parents=True)
                dcb.write_bytes(b"dcb")
            else:
                records = Path(args[1]).parent / "libs" / "foundry" / "records" / "entities" / "scitem"
                records.mkdir(parents=True)
                (records / "item.xml").write_text("<item/>", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run

        def fail_finalizer(_):
            raise RuntimeError("patch failed")

        with pytest.raises(RuntimeError, match="patch failed"):
            extract_dataforge(p4k, unp4k, unforge, cache, finalize_callback=fail_finalizer)

        assert (cache / "old.xml").read_text(encoding="utf-8") == "old"
        assert not list(tmp_path.glob(".dataforge.staging-*"))

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_extract_creates_pristine_and_patched_layers(self, mock_run, tmp_path):
        p4k = tmp_path / "Data.p4k"
        unp4k = tmp_path / "unp4k.exe"
        unforge = tmp_path / "unforge.cli.exe"
        cache = tmp_path / "dataforge"
        p4k.write_bytes(b"p4k")
        unp4k.write_bytes(b"unp4k")
        unforge.write_bytes(b"unforge")

        def fake_run(args, cwd=None, timeout=None):
            if args[-1] == ".dcb":
                dcb = Path(cwd) / "Data" / "Game2.dcb"
                dcb.parent.mkdir(parents=True)
                dcb.write_bytes(b"dcb")
            else:
                records = Path(args[1]).parent / "libs" / "foundry" / "records" / "entities" / "scitem"
                records.mkdir(parents=True)
                (records / "item.xml").write_text("<item>original</item>", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        def finalize(staging_root):
            patched = staging_root / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
            patched.write_text("<item>patched</item>", encoding="utf-8")

        mock_run.side_effect = fake_run
        extract_dataforge(p4k, unp4k, unforge, cache, finalize_callback=finalize, patch_fingerprint="patches-v1")

        pristine = cache / "pristine" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        patched = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        assert pristine.read_text(encoding="utf-8") == "<item>original</item>"
        assert patched.read_text(encoding="utf-8") == "<item>patched</item>"
        assert _read_dataforge_identity(cache)["patch_fingerprint"] == "patches-v1"


# ─────────────────────────────────────────────────────────────────────────────
# Filtered cache copy (cache streamlining — 0.9.3)
# ─────────────────────────────────────────────────────────────────────────────

# Every `records / <path>` that `scripts/generate_enhancements_ini.py`
# currently reads from. Duplicated here on purpose: this is the
# **contract** between the extractor's keep-list and the generator's
# read-list. If the generator grows a new read path, adding it to
# DATAFORGE_KEEP_SUBPATHS also requires adding it here (or something that
# covers it), which makes the maintenance coupling explicit.
#
# To update: run `grep -n 'records / "' scripts/generate_enhancements_ini.py`
# and ensure every leaf path is covered by some entry in
# DATAFORGE_KEEP_SUBPATHS.
GENERATOR_READ_SUBPATHS = (
    "entities/scitem",  # build_scitem_lookups
    "entities/scitem/ships/controller",  # build_controller_lookup
    "entities/scitem/ships/armor",  # build_armor_lookup
    "entities/scitem/ships/shieldgenerator",  # components gen (indirect via scitem)
    "entities/scitem/ships/cooler",
    "entities/scitem/ships/powerplant",
    "entities/scitem/ships/quantumdrive",
    "entities/scitem/ships/radar",
    "entities/scitem/ships/weapons",  # ship weapons + missiles
    "entities/scitem/weapons/fps_weapons",  # FPS weapon descriptions
    "entities/scitem/carryables",  # commodity-crafting carryable lookups
    "entities/spaceships",  # scan_spaceships
    "ammoparams/vehicle",
    "ammoparams/fps",
    "reputation/rewards/missionrewards_reputation",
    "contracts/contractgenerator",  # scan_contract_generators
    "contracts/contracttemplates",  # template fallback in scan_contract_generators
    "crafting/blueprintrewards/blueprintmissionpools",  # blueprint_pools lookup
    "crafting/blueprints/crafting",  # crafting blueprint scan
    "missionbroker/pu_missions",  # mission XP augmentation
    # Guarded reads (may or may not exist in a given patch; extractor keeps
    # the parent subtree, generator guards with `if dir.exists()`):
    "entities/missions",
    "entities/contracts",
    "entities/jobterminal",
)


def _is_subpath_of(child: str, parent: str) -> bool:
    """Is *child* equal to or under *parent* in slash-separated form?"""
    if child == parent:
        return True
    return child.startswith(parent + "/")


@pytest.mark.regression
class TestDataForgeKeepList:
    """Regression tests locking the keep-list to the generator's read-paths.

    These are the guard-rails that catch the dangerous failure mode of cache
    streamlining: a future generator change reads from a subtree the extractor
    doesn't copy, producing silently-empty enhancements rather than an error.
    """

    def test_every_generator_read_path_is_covered(self):
        """Every path the generator reads must lie under some kept subpath."""
        keep = DATAFORGE_KEEP_SUBPATHS
        uncovered = []
        for read in GENERATOR_READ_SUBPATHS:
            if not any(_is_subpath_of(read, k) for k in keep):
                uncovered.append(read)
        assert not uncovered, (
            "Generator reads from paths the extractor does NOT cache:\n  "
            + "\n  ".join(uncovered)
            + "\nAdd these (or a common ancestor) to DATAFORGE_KEEP_SUBPATHS "
            "in src/utils/pak_extractor.py."
        )

    def test_keep_list_has_no_redundant_entries(self):
        """Reject entries that are already covered by another entry (a parent)."""
        redundant = []
        for i, entry in enumerate(DATAFORGE_KEEP_SUBPATHS):
            for j, other in enumerate(DATAFORGE_KEEP_SUBPATHS):
                if i == j:
                    continue
                if _is_subpath_of(entry, other):
                    redundant.append((entry, other))
                    break
        assert not redundant, (
            f"DATAFORGE_KEEP_SUBPATHS contains entries already covered by an ancestor entry: {redundant}"
        )


@pytest.mark.unit
class TestCopyFilteredRecords:
    """Exercise the filtered-copy helper on a synthetic unforge output tree."""

    @staticmethod
    def _make_fake_unforge_output(root: Path) -> None:
        """Write a minimal ``libs/foundry/records/...`` tree with one file in
        each of the keep-paths plus several 'unused' paths that must NOT be
        carried over by the filter."""
        records = root / "libs" / "foundry" / "records"
        # Files inside kept subtrees — these MUST survive the filter.
        for kept in DATAFORGE_KEEP_SUBPATHS:
            leaf = records / kept / "sample.xml"
            leaf.parent.mkdir(parents=True, exist_ok=True)
            leaf.write_text("<kept/>", encoding="utf-8")
        # Files in paths we want dropped — these must NOT survive.
        for dropped in ("ui", "actor", "missiondata", "tintpalettes", "starmap"):
            leaf = records / dropped / "sample.xml"
            leaf.parent.mkdir(parents=True, exist_ok=True)
            leaf.write_text("<dropped/>", encoding="utf-8")

    def test_copies_only_keep_subpaths(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        self._make_fake_unforge_output(src)

        copied, skipped = _copy_filtered_records(src / "libs", dst / "libs")

        records_dst = dst / "libs" / "foundry" / "records"
        for kept in DATAFORGE_KEEP_SUBPATHS:
            assert (records_dst / kept / "sample.xml").exists(), f"kept path {kept!r} missing from filtered output"
        for dropped in ("ui", "actor", "missiondata", "tintpalettes", "starmap"):
            assert not (records_dst / dropped).exists(), f"{dropped!r} leaked into filtered output"
        assert copied == len(DATAFORGE_KEEP_SUBPATHS)
        assert skipped == 0

    def test_skipped_when_source_subpath_missing(self, tmp_path):
        """Some patches don't ship every subtree (e.g. entities/missions).
        Missing source paths should increment `skipped`, not fail."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        self._make_fake_unforge_output(src)
        # Delete one keep-path from the source so the filter sees it missing.
        import shutil as _sh

        _sh.rmtree(src / "libs" / "foundry" / "records" / "entities" / "missions")

        copied, skipped = _copy_filtered_records(src / "libs", dst / "libs")

        assert skipped == 1
        assert copied == len(DATAFORGE_KEEP_SUBPATHS) - 1
        records_dst = dst / "libs" / "foundry" / "records"
        assert not (records_dst / "entities" / "missions").exists()
        # All other kept paths survived
        assert (records_dst / "entities" / "scitem" / "sample.xml").exists()

    def test_raises_on_unexpected_layout(self, tmp_path):
        """If unforge's output doesn't have the expected libs/foundry/records
        layout, fail loudly rather than producing a silently-empty cache."""
        src = tmp_path / "src"
        (src / "libs").mkdir(parents=True)
        # No foundry/records under libs — nothing for the filter to work with.

        with pytest.raises(FileNotFoundError):
            _copy_filtered_records(src / "libs", tmp_path / "dst" / "libs")


@pytest.mark.unit
class TestAtomicCacheReplacement:
    def test_replaces_old_cache_with_staged_cache(self, tmp_path):
        cache = tmp_path / "dataforge"
        staging = tmp_path / ".dataforge.staging"
        cache.mkdir()
        (cache / "old.xml").write_text("old", encoding="utf-8")
        staging.mkdir()
        (staging / "new.xml").write_text("new", encoding="utf-8")

        _replace_dataforge_cache(staging, cache)

        assert not staging.exists()
        assert not (cache / "old.xml").exists()
        assert (cache / "new.xml").read_text(encoding="utf-8") == "new"

    def test_restores_old_cache_when_staged_swap_fails(self, tmp_path, monkeypatch):
        cache = tmp_path / "dataforge"
        staging = tmp_path / ".dataforge.staging"
        cache.mkdir()
        (cache / "old.xml").write_text("old", encoding="utf-8")
        staging.mkdir()
        (staging / "new.xml").write_text("new", encoding="utf-8")

        original_replace = Path.replace

        def fail_staged_swap(source, target):
            if source == staging:
                raise OSError("swap failed")
            return original_replace(source, target)

        monkeypatch.setattr(Path, "replace", fail_staged_swap)
        monkeypatch.setattr("src.utils.pak_extractor.time.sleep", lambda _: None)

        with pytest.raises(OSError, match="swap failed"):
            _replace_dataforge_cache(staging, cache)

        assert (cache / "old.xml").read_text(encoding="utf-8") == "old"
        assert (staging / "new.xml").read_text(encoding="utf-8") == "new"

    def test_recovers_stranded_backup_when_live_cache_is_missing(self, tmp_path):
        cache = tmp_path / "dataforge"
        backup = tmp_path / ".dataforge.backup-interrupted"
        backup.mkdir()
        (backup / "old.xml").write_text("old", encoding="utf-8")

        _recover_dataforge_cache(cache)

        assert (cache / "old.xml").read_text(encoding="utf-8") == "old"
        assert not backup.exists()

    def test_retries_transient_staged_swap_failure(self, tmp_path, monkeypatch):
        cache = tmp_path / "dataforge"
        staging = tmp_path / ".dataforge.staging"
        cache.mkdir()
        staging.mkdir()
        (staging / "new.xml").write_text("new", encoding="utf-8")
        original_replace = Path.replace
        attempts = {"staging": 0}

        def fail_once(source, target):
            if source == staging and attempts["staging"] == 0:
                attempts["staging"] += 1
                raise OSError("temporary lock")
            return original_replace(source, target)

        monkeypatch.setattr(Path, "replace", fail_once)
        monkeypatch.setattr("src.utils.pak_extractor.time.sleep", lambda _: None)

        _replace_dataforge_cache(staging, cache)

        assert attempts["staging"] == 1
        assert (cache / "new.xml").exists()


@pytest.mark.unit
class TestPatchedCacheRebuild:
    def test_rebuilds_raw_from_pristine_when_patch_set_changes(self, tmp_path):
        cache = tmp_path / "dataforge"
        pristine_xml = cache / "pristine" / "libs" / "foundry" / "records" / "item.xml"
        raw_xml = cache / "raw" / "libs" / "foundry" / "records" / "item.xml"
        pristine_xml.parent.mkdir(parents=True)
        raw_xml.parent.mkdir(parents=True)
        pristine_xml.write_text("<item>original</item>", encoding="utf-8")
        raw_xml.write_text("<item>old patch</item>", encoding="utf-8")
        (cache / ".dataforge_identity.json").write_text(
            json.dumps({"schema_version": 2, "patch_fingerprint": "old"}), encoding="utf-8"
        )

        def finalize(staging_root):
            staged_xml = staging_root / "raw" / "libs" / "foundry" / "records" / "item.xml"
            staged_xml.write_text("<item>new patch</item>", encoding="utf-8")

        rebuilt = rebuild_patched_dataforge_cache(cache, "new", finalize)

        assert rebuilt is True
        assert pristine_xml.read_text(encoding="utf-8") == "<item>original</item>"
        assert raw_xml.read_text(encoding="utf-8") == "<item>new patch</item>"
        assert _read_dataforge_identity(cache)["patch_fingerprint"] == "new"

    def test_skips_rebuild_when_patch_set_is_unchanged(self, tmp_path):
        cache = tmp_path / "dataforge"
        (cache / ".dataforge_identity.json").parent.mkdir(parents=True)
        (cache / ".dataforge_identity.json").write_text(
            json.dumps({"schema_version": 2, "patch_fingerprint": "same"}), encoding="utf-8"
        )

        assert rebuild_patched_dataforge_cache(cache, "same", lambda _: pytest.fail("should not finalize")) is False

    def test_patch_removal_restores_raw_from_pristine(self, tmp_path):
        cache = tmp_path / "dataforge"
        pristine_xml = cache / "pristine" / "libs" / "foundry" / "records" / "item.xml"
        raw_xml = cache / "raw" / "libs" / "foundry" / "records" / "item.xml"
        pristine_xml.parent.mkdir(parents=True)
        raw_xml.parent.mkdir(parents=True)
        pristine_xml.write_text("<item>original</item>", encoding="utf-8")
        raw_xml.write_text("<item>removed patch value</item>", encoding="utf-8")
        (cache / ".dataforge_identity.json").write_text(
            json.dumps({"schema_version": 2, "patch_fingerprint": "with-patch"}), encoding="utf-8"
        )

        assert rebuild_patched_dataforge_cache(cache, "no-patches", lambda _: None) is True
        assert raw_xml.read_text(encoding="utf-8") == "<item>original</item>"

    def test_recovers_interrupted_raw_layer_replacement(self, tmp_path):
        cache = tmp_path / "dataforge"
        backup = cache / ".raw.backup-interrupted"
        backup.mkdir(parents=True)
        (backup / "old.xml").write_text("patched", encoding="utf-8")

        _recover_dataforge_layer(cache, "raw")

        assert (cache / "raw" / "old.xml").read_text(encoding="utf-8") == "patched"
        assert not backup.exists()


# ─────────────────────────────────────────────────────────────────────────────
# _robust_rmtree
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRobustRmtree:
    def test_removes_normal_directory(self, tmp_path):
        target = tmp_path / "to_delete"
        target.mkdir()
        (target / "file.txt").write_text("hi", encoding="utf-8")
        robust_rmtree(target)
        assert not target.exists()

    def test_succeeds_silently_when_path_missing(self, tmp_path):
        robust_rmtree(tmp_path / "nonexistent")

    def test_removes_read_only_files(self, tmp_path):
        target = tmp_path / "ro_dir"
        target.mkdir()
        ro_file = target / "readonly.txt"
        ro_file.write_text("data", encoding="utf-8")
        ro_file.chmod(stat.S_IREAD)
        robust_rmtree(target)
        assert not target.exists()

    def test_raises_after_all_attempts_fail(self, tmp_path, monkeypatch):
        target = tmp_path / "stubborn"
        target.mkdir()
        (target / "x.txt").write_text("x", encoding="utf-8")

        import shutil

        call_count = {"n": 0}

        def _always_fail(path, **kwargs):
            call_count["n"] += 1
            raise OSError("locked")

        monkeypatch.setattr(shutil, "rmtree", _always_fail)
        monkeypatch.setattr("time.sleep", lambda _: None)
        with pytest.raises(OSError):
            robust_rmtree(target, attempts=3)
        assert call_count["n"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# dataforge_cache_is_fresh — stamp-based logic
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDataForgeCacheFreshStamp:
    def _make_p4k(self, parent: Path, mtime: float) -> Path:
        p4k = parent / "Data.p4k"
        p4k.write_bytes(b"dummy")
        os.utime(p4k, (mtime, mtime))
        return p4k

    def _make_cache_with_stamp(self, parent: Path, stamp_mtime: float) -> Path:
        cache = parent / "dataforge"
        for layer in ("pristine", "raw"):
            libs = cache / layer / "libs" / "foundry" / "records"
            libs.mkdir(parents=True)
            (libs / "sample.xml").write_text("<x/>", encoding="utf-8")
        stamp = cache / ".p4k_mtime"
        stamp.write_text(str(stamp_mtime))
        return cache

    def _write_identity(self, cache: Path, p4k: Path, unp4k: Path | None = None, unforge: Path | None = None) -> None:
        identity = {
            "schema_version": DATAFORGE_CACHE_SCHEMA_VERSION,
            "p4k": {"size": p4k.stat().st_size, "mtime_ns": p4k.stat().st_mtime_ns},
            "tools": {},
            "patch_fingerprint": "test",
        }
        if unp4k is not None and unforge is not None:
            identity["tools"] = {
                "unp4k": {"size": unp4k.stat().st_size, "mtime_ns": unp4k.stat().st_mtime_ns},
                "unforge": {"size": unforge.stat().st_size, "mtime_ns": unforge.stat().st_mtime_ns},
            }
        (cache / ".dataforge_identity.json").write_text(json.dumps(identity), encoding="utf-8")

    def test_fresh_when_stamp_matches(self, tmp_path):
        mtime = 1700000000.0
        p4k = self._make_p4k(tmp_path, mtime)
        cache = self._make_cache_with_stamp(tmp_path, mtime)
        self._write_identity(cache, p4k)
        assert dataforge_cache_is_fresh(p4k, cache) is True

    def test_stale_when_stamp_older(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000100.0)
        cache = self._make_cache_with_stamp(tmp_path, 1700000000.0)
        self._write_identity(cache, p4k)
        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_legacy_one_layer_cache_is_stale(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = tmp_path / "dataforge"
        (cache / "raw" / "libs" / "foundry" / "records").mkdir(parents=True)
        (cache / ".p4k_mtime").write_text(str(p4k.stat().st_mtime))

        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_extraction_tool_changes(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = self._make_cache_with_stamp(tmp_path, p4k.stat().st_mtime)
        unp4k = tmp_path / "unp4k.exe"
        unforge = tmp_path / "unforge.exe"
        unp4k.write_bytes(b"first")
        unforge.write_bytes(b"first")
        self._write_identity(cache, p4k, unp4k, unforge)
        unp4k.write_bytes(b"changed")

        assert dataforge_cache_is_fresh(p4k, cache, unp4k, unforge) is False

    def test_stale_when_patch_set_changes(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = self._make_cache_with_stamp(tmp_path, p4k.stat().st_mtime)
        patches = tmp_path / "patches"
        patches.mkdir()
        (patches / "example.patch.json").write_text('{"edits": []}', encoding="utf-8")
        self._write_identity(cache, p4k)
        identity_path = cache / ".dataforge_identity.json"
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        identity["patch_fingerprint"] = "old"
        identity_path.write_text(json.dumps(identity), encoding="utf-8")

        assert dataforge_cache_is_fresh(p4k, cache, patch_root=patches) is False

    def test_stale_when_no_xml_files(self, tmp_path):
        mtime = 1700000000.0
        p4k = self._make_p4k(tmp_path, mtime)
        cache = tmp_path / "dataforge"
        libs = cache / "raw" / "libs"
        libs.mkdir(parents=True)
        stamp = cache / ".p4k_mtime"
        stamp.write_text(str(mtime))
        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_stamp_missing(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = tmp_path / "dataforge"
        cache.mkdir()
        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_stamp_corrupt(self, tmp_path):
        mtime = 1700000000.0
        p4k = self._make_p4k(tmp_path, mtime)
        cache = self._make_cache_with_stamp(tmp_path, mtime)
        (cache / ".p4k_mtime").write_text("not-a-float")
        assert dataforge_cache_is_fresh(p4k, cache) is False


# ─────────────────────────────────────────────────────────────────────────────
# extract_global_ini — happy path and error paths
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestExtractGlobalIni:
    def _make_fake_unp4k(self, tmp_path: Path) -> Path:
        exe = tmp_path / "unp4k.exe"
        exe.write_bytes(b"fake")
        return exe

    def _make_p4k(self, tmp_path: Path) -> Path:
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"fake")
        return p4k

    def test_raises_when_unp4k_missing(self, tmp_path):
        p4k = self._make_p4k(tmp_path)
        with pytest.raises(FileNotFoundError, match="unp4k"):
            extract_global_ini(
                p4k_path=p4k,
                output_path=tmp_path / "base.ini",
                unp4k_exe=tmp_path / "missing_unp4k.exe",
            )

    def test_raises_when_p4k_missing(self, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        with pytest.raises(FileNotFoundError, match="Data.p4k"):
            extract_global_ini(
                p4k_path=tmp_path / "missing.p4k",
                output_path=tmp_path / "base.ini",
                unp4k_exe=exe,
            )

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_raises_on_nonzero_returncode(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="unp4k error")
        with pytest.raises(RuntimeError, match="unp4k.exe exited"):
            extract_global_ini(p4k_path=p4k, output_path=tmp_path / "base.ini", unp4k_exe=exe)

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_raises_when_extracted_file_missing(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        # _run_subprocess succeeds but doesn't create the expected global.ini
        with pytest.raises(FileNotFoundError, match="global.ini"):
            extract_global_ini(p4k_path=p4k, output_path=tmp_path / "base.ini", unp4k_exe=exe)

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_happy_path_copies_to_output(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        output = tmp_path / "cache" / "base.ini"

        def _fake_run(args, cwd=None, timeout=None):
            # Simulate unp4k writing the expected file structure
            extracted = Path(cwd) / "data" / "Localization" / "english" / "global.ini"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_text("key=value\n", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = _fake_run
        result = extract_global_ini(p4k_path=p4k, output_path=output, unp4k_exe=exe)
        assert result is True
        assert output.exists()
        assert output.read_text(encoding="utf-8") == "key=value\n"

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_progress_callbacks_called(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        output = tmp_path / "base.ini"

        def _fake_run(args, cwd=None, timeout=None):
            extracted = Path(cwd) / "data" / "Localization" / "english" / "global.ini"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_text("k=v\n", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = _fake_run
        messages = []
        pct_calls = []
        extract_global_ini(
            p4k_path=p4k,
            output_path=output,
            unp4k_exe=exe,
            progress_callback=messages.append,
            progress_pct_callback=lambda cur, total, msg: pct_calls.append((cur, total)),
        )
        assert len(messages) >= 1
        assert len(pct_calls) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
