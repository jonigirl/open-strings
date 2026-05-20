"""Tests for the Enhanced status in src.utils.string_loader._determine_status_from_source."""

from __future__ import annotations

import pytest
from src.utils.string_loader import _determine_status_from_source

pytestmark = pytest.mark.unit


class TestStatusClassification:
    def test_user_source_is_modified(self):
        assert _determine_status_from_source("user", "global") == "Modified"

    def test_enhancements_source_is_enhanced(self):
        """The synthetic 'enhancements' source must return 'Enhanced', not 'Modified'.
        This is the core invariant that lets users filter by Enhanced vs Modified."""
        assert _determine_status_from_source("enhancements", "global") == "Enhanced"

    def test_base_source_is_unmodified(self):
        assert _determine_status_from_source("global", "global") == "Unmodified"

    def test_base_source_with_custom_base_name(self):
        """base_source is parameterised — confirm the rule is 'source equals
        base_source', not 'source is literally global'."""
        assert _determine_status_from_source("custom_base", "custom_base") == "Unmodified"

    def test_other_higher_priority_source_is_modified(self):
        """Generic fallback: any non-base, non-user, non-enhancements source
        returns Modified. Rare post-1.0 but kept as the safe default."""
        assert _determine_status_from_source("contracts", "global") == "Modified"
        assert _determine_status_from_source("ships", "global") == "Modified"

    def test_enhancements_precedes_modified_fallback(self):
        """Regression guard: if the function order were changed so the generic
        Modified-fallback ran before the enhancements check, this catches it."""
        result = _determine_status_from_source("enhancements", "enhancements")
        # Even when base_source == "enhancements", the enhancements branch fires first
        assert result == "Enhanced"
