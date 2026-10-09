"""Tests for src.utils.entry_filter.filter_entry_indices."""

import pytest
from src.models.string_model import StringEntry
from src.utils.entry_filter import _NUM_FILTER_COLUMNS, filter_entry_indices

pytestmark = pytest.mark.unit


def test_num_filter_columns_matches_model():
    from src.gui.string_table_model import NUM_COLUMNS

    assert _NUM_FILTER_COLUMNS == NUM_COLUMNS, (
        f"entry_filter._NUM_FILTER_COLUMNS ({_NUM_FILTER_COLUMNS}) is out of sync with "
        f"string_table_model.NUM_COLUMNS ({NUM_COLUMNS}); update entry_filter.py"
    )


def _e(key="k", category="Ships", original_value="val", custom_value="", status="Unmodified"):
    return StringEntry(
        key=key,
        source_file="global",
        category=category,
        original_value=original_value,
        custom_value=custom_value,
        status=status,
    )


def _no_filters():
    return ["", "", "", "", "", "", ""]


def test_no_filters_returns_all_indices():
    entries = [_e("k1"), _e("k2"), _e("k3")]
    result = filter_entry_indices(entries, {}, _no_filters(), "All", "All", False, False, "★")
    assert result == [0, 1, 2]


def test_empty_entries_returns_empty():
    result = filter_entry_indices([], {}, _no_filters(), "All", "All", False, False, "★")
    assert result == []


def test_hide_unmodified_removes_unmodified_entries():
    entries = [_e("k1", status="Unmodified"), _e("k2", status="Modified")]
    result = filter_entry_indices(entries, {}, _no_filters(), "All", "All", True, False, "★")
    assert result == [1]


def test_category_filter_excludes_non_matching():
    entries = [_e("k1", category="Ships"), _e("k2", category="Gear")]
    result = filter_entry_indices(entries, {}, _no_filters(), "Ships", "All", False, False, "★")
    assert result == [0]


def test_status_filter_excludes_non_matching():
    entries = [_e("k1", status="Unmodified"), _e("k2", status="New")]
    col_filters = _no_filters()
    result = filter_entry_indices(entries, {}, col_filters, "All", "New", False, False, "★")
    assert result == [1]


def test_favorites_only_keeps_entries_starting_with_prefix():
    entries = [_e("k1", custom_value="★ favorite"), _e("k2", custom_value="plain")]
    result = filter_entry_indices(entries, {}, _no_filters(), "All", "All", False, True, "★")
    assert result == [0]


def test_column_filter_by_key():
    entries = [_e("alpha"), _e("beta"), _e("gamma")]
    col_filters = ["", "bet", "", "", "", "", ""]
    result = filter_entry_indices(entries, {}, col_filters, "All", "All", False, False, "★")
    assert result == [1]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("contains", [0, 1, 2]), ("exact", [0]), ("starts_with", [0, 1]), ("excludes", [3])],
)
def test_column_match_modes_are_case_insensitive(mode, expected):
    entries = [_e("Alpha"), _e("alphabet"), _e("prefix_ALPHA"), _e("beta")]
    result = filter_entry_indices(
        entries,
        {},
        ["", "ALPHA"],
        "All",
        "All",
        False,
        False,
        "★",
        column_filter_modes=["contains", mode],
    )
    assert result == expected


def test_column_dropdowns_combine_with_text_modes():
    entries = [
        _e("alpha", category="Ships", custom_value="★ custom", status="Modified"),
        _e("alphabet", category="Ships", custom_value="custom", status="Modified"),
        _e("alpha", category="Gear", custom_value="★ custom", status="Modified"),
    ]
    result = filter_entry_indices(
        entries,
        {},
        ["Ships", "alpha", "", "", "★", "", "Modified"],
        "All",
        "All",
        False,
        False,
        "★",
        column_filter_modes=["exact", "starts_with", "contains", "contains", "exact", "contains", "exact"],
    )
    assert result == [0]


def test_not_favourite_column_filter_matches_displayed_star():
    entries = [_e("ship", custom_value="★ custom"), _e("plain"), _e("gear", category="Gear", custom_value="★ custom")]
    result = filter_entry_indices(
        entries,
        {},
        ["", "", "", "", "★"],
        "All",
        "All",
        False,
        False,
        "★",
        column_filter_modes=["contains"] * 4 + ["excludes"],
    )
    assert result == [1, 2]


def test_empty_excludes_filter_does_not_hide_rows():
    assert filter_entry_indices(
        [_e()],
        {},
        _no_filters(),
        "All",
        "All",
        False,
        False,
        "★",
        column_filter_modes=["excludes"] * 7,
    ) == [0]


def test_column_filter_by_status_text():
    entries = [_e("k1", status="Unmodified"), _e("k2", status="New")]
    col_filters = ["", "", "", "", "", "", "new"]
    result = filter_entry_indices(entries, {}, col_filters, "All", "All", False, False, "★")
    assert result == [1]


def test_column_filter_by_default_values():
    entries = [_e("k1"), _e("k2")]
    default_vals = {"k1": "searchterm"}
    col_filters = ["", "", "searchterm", "", "", "", ""]
    result = filter_entry_indices(entries, default_vals, col_filters, "All", "All", False, False, "★")
    assert result == [0]


def test_out_of_bounds_column_filter_skipped_with_warning(caplog):
    import logging

    entries = [_e("k1"), _e("k2")]
    # Index 99 is way out of range — should be dropped, not raise IndexError
    col_filters = ["", "", "", "", "", "", "", "", "", "", "sometext"]  # 11 items, index 10 is OOB
    with caplog.at_level(logging.WARNING, logger="src.utils.entry_filter"):
        result = filter_entry_indices(entries, {}, col_filters, "All", "All", False, False, "★")
    assert result == [0, 1]  # OOB filter dropped → all entries visible
    assert any("out of range" in rec.message.lower() for rec in caplog.records)
