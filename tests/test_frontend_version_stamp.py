"""Tests for the Frontend_PU_Version watermark applied at apply-to-game time."""

from unittest.mock import patch

import pytest
from src.utils.preview_renderer import (
    _FRONTEND_VERSION_KEY,
    _FRONTEND_VERSION_STAMP_RE,
    _stamp_frontend_version,
)


@pytest.fixture
def mock_version():
    with patch("src.utils.preview_renderer.get_version", return_value="1.3.1"):
        yield "1.3.1"


class TestFrontendVersionStamp:
    def test_appends_watermark_to_stock_value(self, mock_version):
        merged = {_FRONTEND_VERSION_KEY: "Star Citizen Alpha 4.8.0 PTU"}
        _stamp_frontend_version(merged)
        assert merged[_FRONTEND_VERSION_KEY] == (
            "Star Citizen Alpha 4.8.0 PTU | Localizations Enhanced with Open Strings v1.3.1"
        )

    def test_skips_when_key_missing(self, mock_version):
        merged = {"SomeOtherKey": "value"}
        _stamp_frontend_version(merged)
        assert _FRONTEND_VERSION_KEY not in merged

    def test_idempotent_same_version(self, mock_version):
        merged = {_FRONTEND_VERSION_KEY: "Star Citizen Alpha 4.8.0 PTU"}
        _stamp_frontend_version(merged)
        once = merged[_FRONTEND_VERSION_KEY]
        _stamp_frontend_version(merged)
        assert merged[_FRONTEND_VERSION_KEY] == once

    def test_rolls_forward_to_new_version(self):
        merged = {
            _FRONTEND_VERSION_KEY: ("Star Citizen Alpha 4.8.0 PTU | Localizations Enhanced with Open Strings v1.3.0")
        }
        with patch("src.utils.preview_renderer.get_version", return_value="1.3.1"):
            _stamp_frontend_version(merged)
        assert merged[_FRONTEND_VERSION_KEY] == (
            "Star Citizen Alpha 4.8.0 PTU | Localizations Enhanced with Open Strings v1.3.1"
        )

    @pytest.mark.parametrize(
        "legacy_suffix",
        [
            # First-cut watermark (heart emoji as text, "by")
            "| Enhanced with <3 by Open Strings v1.3.0",
            "| Enhanced with <3 by Open Strings 1.2.9",
            # Second-cut watermark ("Enhanced by", no v)
            "| Localizations Enhanced by Open Strings 1.3.0",
            "| Localizations Enhanced by Open Strings v1.3.0",
        ],
    )
    def test_strips_legacy_phrasings(self, mock_version, legacy_suffix):
        # Every prior on-disk watermark wording must be stripped, not
        # left to accumulate, so users who applied with an earlier
        # build get the current phrasing on next Apply.
        merged = {_FRONTEND_VERSION_KEY: f"Star Citizen Alpha 4.8.0 PTU {legacy_suffix}"}
        _stamp_frontend_version(merged)
        assert merged[_FRONTEND_VERSION_KEY] == (
            "Star Citizen Alpha 4.8.0 PTU | Localizations Enhanced with Open Strings v1.3.1"
        )

    def test_preserves_user_edited_base_value(self, mock_version):
        merged = {_FRONTEND_VERSION_KEY: "My Custom Build"}
        _stamp_frontend_version(merged)
        assert merged[_FRONTEND_VERSION_KEY] == ("My Custom Build | Localizations Enhanced with Open Strings v1.3.1")

    def test_stamp_regex_matches_with_extra_whitespace(self):
        cases = [
            " | Localizations Enhanced with Open Strings v1.3.1",
            "  |  Localizations Enhanced with Open Strings v1.3.1",
            " | Localizations Enhanced with Open Strings 1.3.1",  # no-v tolerated
            " | Localizations Enhanced with Open Strings v1.3.1   ",
        ]
        for suffix in cases:
            full = "Base value" + suffix
            assert _FRONTEND_VERSION_STAMP_RE.search(full), f"regex did not match expected suffix: {suffix!r}"

    def test_does_not_strip_pipe_in_base_value(self, mock_version):
        # Plain pipe in the middle isn't our watermark — leave it alone.
        merged = {_FRONTEND_VERSION_KEY: "Star Citizen | Build A"}
        _stamp_frontend_version(merged)
        assert merged[_FRONTEND_VERSION_KEY] == (
            "Star Citizen | Build A | Localizations Enhanced with Open Strings v1.3.1"
        )
