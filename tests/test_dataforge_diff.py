"""Tests for src.utils.dataforge_diff."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.utils.dataforge_diff import (
    CATEGORY_SUBTREES,
    MANIFEST_FILE,
    _hash_file,
    dirty_categories,
    update_manifest,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_xml(path: Path, content: str = "<root/>") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _hash_file
# ---------------------------------------------------------------------------


class TestHashFile:
    def test_returns_hex_string(self, tmp_path: Path) -> None:
        f = tmp_path / "a.xml"
        f.write_bytes(b"hello")
        result = _hash_file(f)
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.xml"
        b = tmp_path / "b.xml"
        a.write_bytes(b"content")
        b.write_bytes(b"content")
        assert _hash_file(a) == _hash_file(b)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.xml"
        b = tmp_path / "b.xml"
        a.write_bytes(b"foo")
        b.write_bytes(b"bar")
        assert _hash_file(a) != _hash_file(b)


# ---------------------------------------------------------------------------
# update_manifest
# ---------------------------------------------------------------------------


class TestUpdateManifest:
    def test_creates_manifest_file(self, tmp_path: Path) -> None:
        _write_xml(tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml")
        update_manifest(tmp_path)
        assert (tmp_path / MANIFEST_FILE).exists()

    def test_manifest_contains_relative_path(self, tmp_path: Path) -> None:
        rel = "foundry/records/entities/spaceships/ship.xml"
        _write_xml(tmp_path / rel)
        update_manifest(tmp_path)
        data = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert rel in data

    def test_manifest_entry_has_mtime_and_sha256(self, tmp_path: Path) -> None:
        rel = "foundry/records/entities/spaceships/ship.xml"
        _write_xml(tmp_path / rel)
        update_manifest(tmp_path)
        data = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))
        entry = data[rel]
        assert "mtime" in entry
        assert "sha256" in entry
        assert len(entry["sha256"]) == 64

    def test_empty_dir_produces_empty_manifest(self, tmp_path: Path) -> None:
        update_manifest(tmp_path)
        data = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert data == {}

    def test_non_xml_files_are_excluded(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("ignored", encoding="utf-8")
        _write_xml(tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml")
        update_manifest(tmp_path)
        data = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert all(k.endswith(".xml") for k in data)

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        for i in range(3):
            _write_xml(tmp_path / "foundry" / "records" / f"file{i}.xml")
        calls: list[tuple] = []
        update_manifest(tmp_path, progress_callback=lambda c, t, m: calls.append((c, t, m)))
        assert calls  # at least one call made


# ---------------------------------------------------------------------------
# dirty_categories
# ---------------------------------------------------------------------------


class TestDirtyCategories:
    def test_returns_none_when_no_manifest(self, tmp_path: Path) -> None:
        _write_xml(tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml")
        result = dirty_categories(tmp_path)
        assert result is None

    def test_returns_empty_set_when_nothing_changed(self, tmp_path: Path) -> None:
        _write_xml(tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml")
        update_manifest(tmp_path)
        result = dirty_categories(tmp_path)
        assert result == set()

    def test_returns_dirty_category_when_file_changes(self, tmp_path: Path) -> None:
        ship = tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml"
        _write_xml(ship, "<root>v1</root>")
        update_manifest(tmp_path)

        ship.write_text("<root>v2</root>", encoding="utf-8")
        # Force mtime difference so the diff check is triggered
        import time

        time.sleep(0.01)
        ship.touch()

        result = dirty_categories(tmp_path)
        assert result is not None
        assert "ships" in result

    def test_returns_empty_set_when_content_unchanged_despite_mtime(self, tmp_path: Path) -> None:
        ship = tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml"
        _write_xml(ship, "<root/>")
        update_manifest(tmp_path)

        # Re-write identical content — same sha256, different mtime
        ship.write_text("<root/>", encoding="utf-8")

        result = dirty_categories(tmp_path)
        assert result == set()

    def test_added_file_triggers_correct_category(self, tmp_path: Path) -> None:
        _write_xml(tmp_path / "foundry" / "records" / "entities" / "spaceships" / "existing.xml")
        update_manifest(tmp_path)

        _write_xml(tmp_path / "foundry" / "records" / "entities" / "spaceships" / "new.xml")
        result = dirty_categories(tmp_path)
        assert result is not None
        assert "ships" in result

    def test_removed_file_triggers_correct_category(self, tmp_path: Path) -> None:
        ship = tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml"
        _write_xml(ship)
        update_manifest(tmp_path)

        ship.unlink()
        result = dirty_categories(tmp_path)
        assert result is not None
        assert "ships" in result

    def test_change_in_untracked_path_returns_empty_dirty(self, tmp_path: Path) -> None:
        known = tmp_path / "foundry" / "records" / "entities" / "spaceships" / "ship.xml"
        _write_xml(known)
        update_manifest(tmp_path)

        # Add a file in a path not covered by any CATEGORY_SUBTREES entry
        _write_xml(tmp_path / "foundry" / "records" / "unknown_category" / "file.xml")
        result = dirty_categories(tmp_path)
        # Result is not None (manifest exists, change detected) but the
        # changed path doesn't map to any known category
        assert result is not None
        assert result == set()


# ---------------------------------------------------------------------------
# CATEGORY_SUBTREES path correctness
# ---------------------------------------------------------------------------


class TestCategorySubtreesPaths:
    """Verify that CATEGORY_SUBTREES paths actually match snapshot entries.

    Paths in the manifest are relative to the libs/ cache_dir, so every
    valid subtree prefix must start with 'foundry/records/'.
    """

    def test_all_prefixes_start_with_foundry_records(self) -> None:
        for category, subtrees in CATEGORY_SUBTREES.items():
            for prefix in subtrees:
                assert prefix.startswith("foundry/records/"), (
                    f"CATEGORY_SUBTREES[{category!r}] has prefix {prefix!r} "
                    "that does not start with 'foundry/records/' — "
                    "paths are relative to libs/ so the foundry/records/ prefix is required"
                )

    def test_ships_category_covers_spaceships(self) -> None:
        test_path = "foundry/records/entities/spaceships/DRAK_Cutlass_Black.xml"
        matches = [cat for cat, subtrees in CATEGORY_SUBTREES.items() if any(test_path.startswith(p) for p in subtrees)]
        assert "ships" in matches, f"'ships' not matched by {test_path!r}"

    def test_missions_category_covers_contractgenerator(self) -> None:
        test_path = "foundry/records/contracts/contractgenerator/vaughn_gen.xml"
        matches = [cat for cat, subtrees in CATEGORY_SUBTREES.items() if any(test_path.startswith(p) for p in subtrees)]
        assert "missions" in matches, f"'missions' not matched by {test_path!r}"

    def test_no_legacy_bare_entities_prefix(self) -> None:
        for category, subtrees in CATEGORY_SUBTREES.items():
            for prefix in subtrees:
                assert not prefix.startswith("entities/"), (
                    f"CATEGORY_SUBTREES[{category!r}] has legacy bare prefix {prefix!r} "
                    "— should start with 'foundry/records/entities/'"
                )

    def test_no_dead_entities_ships_path(self) -> None:
        all_prefixes = [p for subtrees in CATEGORY_SUBTREES.values() for p in subtrees]
        assert "entities/ships" not in all_prefixes
        assert "foundry/records/entities/ships" not in all_prefixes

    def test_no_dead_itemports_path(self) -> None:
        all_prefixes = [p for subtrees in CATEGORY_SUBTREES.values() for p in subtrees]
        assert "entities/itemports" not in all_prefixes
        assert "foundry/records/entities/itemports" not in all_prefixes
