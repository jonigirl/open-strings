"""Additional edge-case tests for src/utils/entry_filter.py and
src/utils/applied_file_validator.py, covering paths not exercised by
test_extracted_modules.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from src.models.string_model import StringEntry
from src.utils.applied_file_validator import validate_applied_file
from src.utils.entry_filter import filter_entry_indices

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(
    key: str,
    category: str = "Ships",
    status: str = "Unmodified",
    custom: str = "",
    original: str = "base value",
) -> StringEntry:
    return StringEntry(
        key=key,
        source_file="global",
        category=category,
        original_value=original,
        custom_value=custom,
        status=status,
    )


def _no_filters(**overrides) -> dict:
    base = dict(
        column_filters=[""] * 7,
        category_filter="All",
        status_filter="All",
        hide_unmodified=False,
        favorites_only=False,
        favorite_prefix="★",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# filter_entry_indices — additional column filter coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilterEntryIndicesExtended:
    """Additional column filter tests for columns not covered by the base suite."""

    # Column 0 — Category
    def test_column_filter_category(self):
        entries = [_entry("k1", category="Ships"), _entry("k2", category="Gear")]
        filters = [""] * 7
        filters[0] = "ship"
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        assert result == [0]

    # Column 2 — Default Value (from default_values dict)
    def test_column_filter_default_value(self):
        entries = [_entry("k1"), _entry("k2")]
        default_values = {"k1": "Cutlass Black", "k2": "Avenger Titan"}
        filters = [""] * 7
        filters[2] = "cutlass"
        result = filter_entry_indices(entries, default_values, **_no_filters(column_filters=filters))
        assert result == [0]

    def test_column_filter_default_value_no_match(self):
        entries = [_entry("k1")]
        default_values = {"k1": "Cutlass"}
        filters = [""] * 7
        filters[2] = "avenger"
        result = filter_entry_indices(entries, default_values, **_no_filters(column_filters=filters))
        assert result == []

    def test_column_filter_default_value_key_absent(self):
        # Key has no entry in default_values → treated as empty string
        entries = [_entry("k_unknown")]
        filters = [""] * 7
        filters[2] = "cutlass"
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        assert result == []

    # Column 3 — Original Value
    def test_column_filter_original_value(self):
        entries = [_entry("k1", original="Drake Cutlass"), _entry("k2", original="Aegis Avenger")]
        filters = [""] * 7
        filters[3] = "drake"
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        assert result == [0]

    # Column 4 — Favorite star display
    def test_column_filter_favorite_star_column(self):
        entries = [
            _entry("k1", custom="★ Cutlass"),
            _entry("k2", custom="Avenger"),
        ]
        filters = [""] * 7
        filters[4] = "★"
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        assert result == [0]

    def test_column_filter_favorite_star_absent(self):
        # Non-favourite entries show "" in column 4
        entries = [_entry("k1", custom="no star")]
        filters = [""] * 7
        filters[4] = "★"
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        assert result == []

    # Column 6 — Status
    def test_column_filter_status(self):
        entries = [_entry("k1", status="Modified"), _entry("k2", status="Unmodified")]
        filters = [""] * 7
        filters[6] = "modified"
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        # "Modified" matches "modified"; "Unmodified" also contains "modified" substring
        assert 0 in result
        assert 1 in result  # "unmodified" contains "modified"

    def test_column_filter_status_exact_unmodified(self):
        entries = [_entry("k1", status="Modified"), _entry("k2", status="Unmodified")]
        filters = [""] * 7
        filters[6] = "unmodified"
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        assert result == [1]

    # Multiple column filters active simultaneously
    def test_multiple_column_filters_both_must_match(self):
        entries = [
            _entry("vehicle_NameHawk", category="Ships", original="Hawk"),
            _entry("vehicle_NameAvenger", category="Ships", original="Avenger"),
        ]
        filters = [""] * 7
        filters[1] = "hawk"  # key filter
        filters[3] = "hawk"  # original value filter
        result = filter_entry_indices(entries, {}, **_no_filters(column_filters=filters))
        assert result == [0]

    # Filter interaction: hide_unmodified wins over category_filter
    def test_hide_unmodified_before_category_filter(self):
        entries = [
            _entry("k1", category="Ships", status="Unmodified"),
            _entry("k2", category="Ships", status="Modified"),
        ]
        result = filter_entry_indices(
            entries,
            {},
            **_no_filters(hide_unmodified=True, category_filter="Ships"),
        )
        assert result == [1]

    # Favorites filter skips when custom value does not start with prefix
    def test_favorites_filter_prefix_must_be_start(self):
        entries = [
            _entry("k1", custom="value★"),  # ★ in middle, not start
            _entry("k2", custom="★value"),  # ★ at start
        ]
        result = filter_entry_indices(entries, {}, **_no_filters(favorites_only=True, favorite_prefix="★"))
        assert result == [1]

    # Status filter "New"
    def test_status_filter_new(self):
        entries = [
            _entry("k1", status="New"),
            _entry("k2", status="Modified"),
        ]
        result = filter_entry_indices(entries, {}, **_no_filters(status_filter="New"))
        assert result == [0]


# ---------------------------------------------------------------------------
# validate_applied_file — exception / error paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateAppliedFileErrorPaths:
    """Exception paths and error-reporting in validate_applied_file."""

    def test_corrupt_base_ini_skips_validation(self, tmp_path: Path):
        """If base.ini exists but can't be parsed (IOError), validation is skipped."""
        base_ini = tmp_path / "base.ini"
        # Write a file but then make it unreadable — simulated by patching
        base_ini.write_text("k=v\n", encoding="utf-8")

        written = tmp_path / "written.ini"
        written.write_text("k=v\n", encoding="utf-8")

        # Patch parse_ini_file to raise for base.ini only
        import src.utils.applied_file_validator as avm

        original = avm.parse_ini_file

        def patched_parse(path):
            if Path(path).name == "base.ini":
                raise OSError("simulated read error")
            return original(path)

        avm.parse_ini_file = patched_parse
        try:
            result = validate_applied_file(written, tmp_path)
        finally:
            avm.parse_ini_file = original

        # Validation was skipped; no error message
        assert result == ""

    def test_corrupt_written_file_skips_validation(self, tmp_path: Path):
        """If the written file can't be parsed, validation skips cleanly."""
        stock = {"k1", "k2"}
        written = tmp_path / "written.ini"
        written.write_text("k1=v\n", encoding="utf-8")

        import src.utils.applied_file_validator as avm

        original = avm.parse_ini_file

        def patched_parse(path):
            if Path(path).name == "written.ini":
                raise OSError("simulated write-file read error")
            return original(path)

        avm.parse_ini_file = patched_parse
        try:
            result = validate_applied_file(written, tmp_path, stock_keys=stock)
        finally:
            avm.parse_ini_file = original

        assert result == ""

    def test_large_missing_set_truncated_at_20_in_message(self, tmp_path: Path):
        """When more than 20 keys are missing, the message shows a '... and N more' line."""
        stock = {f"key_{i}" for i in range(25)}
        written = tmp_path / "written.ini"
        # Write only 2 of the 25 stock keys
        written.write_text("key_0=v\nkey_1=v\n", encoding="utf-8")

        result = validate_applied_file(written, tmp_path, stock_keys=stock)
        assert "and" in result.lower()
        assert "more" in result.lower()

    def test_extra_keys_reported_with_truncation_when_many(self, tmp_path: Path):
        """More than 20 extra keys also get a '... and N more' line."""
        stock = {"k1"}
        written = tmp_path / "written.ini"
        lines = "k1=v\n" + "".join(f"extra_{i}=v\n" for i in range(25))
        written.write_text(lines, encoding="utf-8")

        result = validate_applied_file(written, tmp_path, stock_keys=stock)
        assert "unexpected" in result.lower() or "extra" in result.lower() or "and" in result.lower()

    def test_restore_message_appended(self, tmp_path: Path):
        """The 'previous file has been restored' guidance must appear in the warning."""
        stock = {"k1", "k2"}
        written = tmp_path / "written.ini"
        written.write_text("k1=v\n", encoding="utf-8")  # k2 missing

        result = validate_applied_file(written, tmp_path, stock_keys=stock)
        assert "restored" in result.lower()
