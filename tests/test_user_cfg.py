"""Tests for ensure_user_cfg_language — guarding against the duplicate-append bug."""

from unittest.mock import patch

import pytest
from src.utils.user_cfg import ensure_user_cfg_language

pytestmark = pytest.mark.unit


@pytest.fixture
def channel_dir(tmp_path):
    """Patch AppSettings so user.cfg lives under a clean tmp dir."""
    with patch("src.utils.user_cfg.AppSettings") as mock_settings:
        mock_settings.get_game_install_path.return_value = str(tmp_path)
        mock_settings.get_active_channel.return_value = "LIVE"
        yield tmp_path


def _user_cfg(channel_dir):
    return (channel_dir / "user.cfg").read_text(encoding="utf-8")


class TestEnsureUserCfgLanguage:
    def test_creates_user_cfg_when_missing(self, channel_dir):
        assert ensure_user_cfg_language() is True
        assert _user_cfg(channel_dir) == "g_language = english\n"

    def test_appends_when_key_absent(self, channel_dir):
        (channel_dir / "user.cfg").write_text("r_VSync = 1\n", encoding="utf-8")
        assert ensure_user_cfg_language() is True
        content = _user_cfg(channel_dir)
        assert content.count("g_language") == 1
        assert "g_language = english" in content
        assert "r_VSync = 1" in content

    @pytest.mark.regression
    @pytest.mark.parametrize(
        "existing_line",
        [
            "g_language = english",  # canonical
            "g_language=english",  # no spaces
            "g_language= english",  # left-tight
            "g_language =english",  # right-tight
            "g_language =  english",  # extra spaces
            "G_Language = english",  # mixed key case
            "g_language = English",  # mixed value case
            "g_language = ENGLISH",  # upper value
            'g_language = "english"',  # quoted value
            "g_language = english   ",  # trailing whitespace
            "g_language = english ; comment",  # trailing comment
        ],
    )
    def test_does_not_duplicate_existing_english_setting(self, channel_dir, existing_line):
        original = f"r_VSync = 1\n{existing_line}\nr_Width = 1920\n"
        (channel_dir / "user.cfg").write_text(original, encoding="utf-8")

        assert ensure_user_cfg_language() is True

        content = _user_cfg(channel_dir)
        # The bug: every spacing/casing variant above used to cause a
        # second canonical line to be appended on each apply.
        assert content.lower().count("g_language") == 1, (
            f"Duplicate g_language appended for input {existing_line!r}\nGot:\n{content}"
        )
        # And we must not have mutated the user's preferred format.
        assert existing_line in content

    def test_leaves_non_english_value_alone(self, channel_dir):
        (channel_dir / "user.cfg").write_text("g_language = french\n", encoding="utf-8")
        assert ensure_user_cfg_language() is True

        content = _user_cfg(channel_dir)
        assert content.count("g_language") == 1
        assert "g_language = french" in content
        assert "english" not in content

    def test_returns_false_when_install_path_unset(self, tmp_path):
        with patch("src.utils.user_cfg.AppSettings") as mock_settings:
            mock_settings.get_game_install_path.return_value = ""
            assert ensure_user_cfg_language() is False

    def test_returns_false_when_install_path_missing(self, tmp_path):
        with patch("src.utils.user_cfg.AppSettings") as mock_settings:
            mock_settings.get_game_install_path.return_value = str(tmp_path / "nope")
            mock_settings.get_active_channel.return_value = "LIVE"
            assert ensure_user_cfg_language() is False

    def test_appends_without_blank_separator_when_file_ends_in_newline(self, channel_dir):
        (channel_dir / "user.cfg").write_text("r_VSync = 1\n\n", encoding="utf-8")
        ensure_user_cfg_language()
        # Should not introduce a spurious second blank line.
        content = _user_cfg(channel_dir)
        assert "\n\n\n" not in content
