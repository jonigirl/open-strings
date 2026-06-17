"""Tests for pending_edits utility functions."""

from __future__ import annotations

import pytest
from src.models.string_model import StringEntry
from src.utils.pending_edits import restore_pending_edits, snapshot_pending_edits

pytestmark = pytest.mark.unit


# ── Helpers ───────────────────────────────────────────────────────────────────


def _entry(key: str, custom: str = "", original: str = "orig") -> StringEntry:
    e = StringEntry.__new__(StringEntry)
    e.key = key
    e.original_value = original
    e.custom_value = custom
    e.status = "Modified" if custom and custom != original else "Unmodified"
    return e


# ── snapshot_pending_edits ────────────────────────────────────────────────────


class TestSnapshotPendingEdits:
    def test_empty_entries_returns_empty_dict(self):
        assert snapshot_pending_edits([]) == {}

    def test_no_custom_values_returns_empty_dict(self):
        entries = [_entry("a"), _entry("b"), _entry("c")]
        assert snapshot_pending_edits(entries) == {}

    def test_captures_entries_with_custom_value(self):
        entries = [_entry("a", "custom_a"), _entry("b"), _entry("c", "custom_c")]
        result = snapshot_pending_edits(entries)
        assert result == {"a": "custom_a", "c": "custom_c"}

    def test_ignores_empty_string_custom_value(self):
        entries = [_entry("a", ""), _entry("b", "val")]
        result = snapshot_pending_edits(entries)
        assert result == {"b": "val"}

    def test_all_entries_have_custom_values(self):
        entries = [_entry("x", "vx"), _entry("y", "vy"), _entry("z", "vz")]
        result = snapshot_pending_edits(entries)
        assert result == {"x": "vx", "y": "vy", "z": "vz"}

    def test_returns_copy_not_reference(self):
        entries = [_entry("a", "val")]
        result = snapshot_pending_edits(entries)
        entries[0].custom_value = "changed"
        assert result["a"] == "val"  # snapshot is not affected


# ── restore_pending_edits ─────────────────────────────────────────────────────


class TestRestorePendingEdits:
    def test_empty_snapshot_returns_zero(self):
        entries = [_entry("a", "val")]
        assert restore_pending_edits(entries, {}) == 0

    def test_empty_entries_returns_zero(self):
        assert restore_pending_edits([], {"a": "val"}) == 0

    def test_restores_matching_key(self):
        entries = [_entry("a")]  # reloaded: no custom value
        count = restore_pending_edits(entries, {"a": "edited"})
        assert count == 1
        assert entries[0].custom_value == "edited"

    def test_status_set_to_modified_when_differs_from_original(self):
        entries = [_entry("a", original="stock")]
        restore_pending_edits(entries, {"a": "custom"})
        assert entries[0].status == "Modified"

    def test_status_set_to_unmodified_when_matches_original(self):
        entries = [_entry("a", original="same")]
        restore_pending_edits(entries, {"a": "same"})
        assert entries[0].status == "Unmodified"

    def test_skips_keys_not_in_entries(self):
        entries = [_entry("b")]
        count = restore_pending_edits(entries, {"a": "val"})
        assert count == 0
        assert entries[0].custom_value == ""

    def test_skips_entry_when_snapshot_matches_current_custom(self):
        entries = [_entry("a", "already_set")]
        count = restore_pending_edits(entries, {"a": "already_set"})
        assert count == 0

    def test_multiple_entries_restored(self):
        entries = [_entry("a"), _entry("b"), _entry("c", "c_existing")]
        snapshot = {"a": "new_a", "b": "new_b"}
        count = restore_pending_edits(entries, snapshot)
        assert count == 2
        assert entries[0].custom_value == "new_a"
        assert entries[1].custom_value == "new_b"
        assert entries[2].custom_value == "c_existing"

    def test_partial_overlap(self):
        entries = [_entry("a"), _entry("b"), _entry("c")]
        snapshot = {"a": "va", "x": "vx"}  # x is not in entries
        count = restore_pending_edits(entries, snapshot)
        assert count == 1
        assert entries[0].custom_value == "va"

    def test_returns_correct_count(self):
        entries = [_entry("a"), _entry("b"), _entry("c")]
        snapshot = {"a": "va", "b": "vb", "c": "vc"}
        count = restore_pending_edits(entries, snapshot)
        assert count == 3

    def test_entries_without_snapshot_match_are_untouched(self):
        entries = [_entry("a"), _entry("b", "existing")]
        restore_pending_edits(entries, {"a": "va"})
        assert entries[1].custom_value == "existing"
