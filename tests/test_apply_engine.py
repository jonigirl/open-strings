"""Tests for src.utils.apply_engine — pure apply-to-game helpers."""

from unittest.mock import patch

import pytest
from src.utils.apply_engine import create_apply_backup, find_apply_base_file

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# create_apply_backup
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateApplyBackup:
    def test_returns_none_when_target_missing(self, tmp_path):
        result = create_apply_backup(tmp_path / "nonexistent.ini", tmp_path / "backups", max_backups=5)
        assert result is None

    def test_creates_backup_file(self, tmp_path):
        target = tmp_path / "global.ini"
        target.write_text("key=value", encoding="utf-8")
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()

        result = create_apply_backup(target, backups_dir, max_backups=5)

        assert result is not None
        assert result.exists()
        assert result.name.startswith("global.ini.bak_")
        assert result.read_text(encoding="utf-8") == "key=value"

    def test_backup_name_includes_timestamp(self, tmp_path):
        target = tmp_path / "global.ini"
        target.write_text("x=1", encoding="utf-8")
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()

        with patch("src.utils.apply_engine.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260617_120000"
            result = create_apply_backup(target, backups_dir, max_backups=5)

        assert result is not None
        assert result.name == "global.ini.bak_20260617_120000"

    def test_prunes_oldest_when_at_limit(self, tmp_path):
        target = tmp_path / "global.ini"
        target.write_text("x=1", encoding="utf-8")
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()

        # Create 5 existing backup files with distinct mtimes
        existing = []
        for i in range(5):
            bak = backups_dir / f"global.ini.bak_2026010{i}_000000"
            bak.write_text(f"backup {i}", encoding="utf-8")
            import os
            import time

            mtime = time.time() - (5 - i) * 3600
            os.utime(bak, (mtime, mtime))
            existing.append(bak)

        create_apply_backup(target, backups_dir, max_backups=5)

        # Oldest (index 0) should have been pruned
        assert not existing[0].exists()
        # Others remain
        for bak in existing[1:]:
            assert bak.exists()

    def test_does_not_prune_when_below_limit(self, tmp_path):
        target = tmp_path / "global.ini"
        target.write_text("x=1", encoding="utf-8")
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()

        existing = []
        for i in range(3):
            bak = backups_dir / f"global.ini.bak_2026010{i}_000000"
            bak.write_text(f"b{i}", encoding="utf-8")
            existing.append(bak)

        create_apply_backup(target, backups_dir, max_backups=5)

        for bak in existing:
            assert bak.exists()


# ─────────────────────────────────────────────────────────────────────────────
# find_apply_base_file
# ─────────────────────────────────────────────────────────────────────────────


class TestFindApplyBaseFile:
    def test_returns_none_when_no_sources(self, tmp_path):
        result = find_apply_base_file(["global", "user"], {}, tmp_path)
        assert result is None

    def test_returns_local_file_when_exists(self, tmp_path):
        local = tmp_path / "base.ini"
        local.write_text("k=v", encoding="utf-8")

        result = find_apply_base_file(["global"], {"global": str(local)}, tmp_path)

        assert result == local

    def test_skips_missing_local_path(self, tmp_path):
        missing = tmp_path / "missing.ini"
        local = tmp_path / "user.ini"
        local.write_text("k=v", encoding="utf-8")

        result = find_apply_base_file(
            ["global", "user"],
            {"global": str(missing), "user": str(local)},
            tmp_path,
        )

        assert result == local

    def test_resolves_url_source_from_cache(self, tmp_path):
        cache_base = tmp_path / "base.ini"
        cache_base.write_text("cached=1", encoding="utf-8")

        result = find_apply_base_file(
            ["global"],
            {"global": "https://example.com/base.ini"},
            tmp_path,
        )

        assert result == cache_base

    def test_url_source_returns_none_when_cache_missing(self, tmp_path):
        result = find_apply_base_file(
            ["global"],
            {"global": "https://example.com/base.ini"},
            tmp_path,
        )
        assert result is None

    def test_respects_hierarchy_order(self, tmp_path):
        first = tmp_path / "global.ini"
        first.write_text("g=1", encoding="utf-8")
        second = tmp_path / "user.ini"
        second.write_text("u=1", encoding="utf-8")

        result = find_apply_base_file(
            ["global", "user"],
            {"global": str(first), "user": str(second)},
            tmp_path,
        )

        assert result == first

    def test_empty_source_path_is_skipped(self, tmp_path):
        local = tmp_path / "user.ini"
        local.write_text("u=1", encoding="utf-8")

        result = find_apply_base_file(
            ["global", "user"],
            {"global": "", "user": str(local)},
            tmp_path,
        )

        assert result == local
