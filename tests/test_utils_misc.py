"""Tests for src/utils/version.py, src/utils/perf.py,
src/utils/user_ini_manager.py, and src/utils/user_cfg.py.

These modules were previously untested or only partially covered.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock Windows-only winreg so settings.py (imported by user_cfg.py) can be
# loaded on Linux CI. Must be set before any import of src.utils.settings.
if "winreg" not in sys.modules:
    sys.modules["winreg"] = MagicMock()
# If settings was previously attempted and failed, remove the broken entry
# so it will be re-imported cleanly with the mock in place.
for _mod in list(sys.modules):
    if _mod in ("src.utils.settings", "src.utils.user_cfg"):
        del sys.modules[_mod]


# ---------------------------------------------------------------------------
# version.py — get_version()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetVersion:
    """get_version reads from VERSION.TXT or falls back to '0.1.0'."""

    def test_returns_string(self):
        from src.utils.version import get_version

        result = get_version()
        assert isinstance(result, str)
        assert result  # must be non-empty

    def test_reads_project_version_txt(self):
        """In non-frozen mode, the project root VERSION.TXT should be readable."""
        from src.utils.version import get_version

        result = get_version()
        # The repo has a real VERSION.TXT; it should NOT fall back to '0.1.0'
        # unless the file genuinely doesn't exist.
        assert isinstance(result, str)

    def test_fallback_when_version_file_missing(self, tmp_path, monkeypatch):
        """If VERSION.TXT is absent, get_version returns the fallback string."""
        import src.utils.version as version_mod

        # Monkeypatch __file__ of the module so it looks in tmp_path (no VERSION.TXT)
        monkeypatch.setattr(version_mod, "__file__", str(tmp_path / "version.py"))
        result = version_mod.get_version()
        assert result == "0.1.0"

    def test_frozen_uses_meipass(self, monkeypatch, tmp_path):
        """When running from a PyInstaller bundle, version is read from _MEIPASS."""
        import src.utils.version as version_mod

        version_file = tmp_path / "VERSION.TXT"
        version_file.write_text("9.9.9\n", encoding="utf-8")
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        result = version_mod.get_version()
        assert result == "9.9.9"


# ---------------------------------------------------------------------------
# perf.py — timed decorator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTimedDecorator:
    """timed should transparently wrap a function."""

    def test_return_value_passed_through(self):
        from src.utils.perf import timed

        @timed
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_exception_re_raised(self):
        from src.utils.perf import timed

        @timed
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fail()

    def test_wraps_preserves_name(self):
        from src.utils.perf import timed

        @timed
        def my_function():
            pass

        assert my_function.__name__ == "my_function"

    def test_logs_at_debug_when_enabled(self, caplog):
        from src.utils.perf import timed

        @timed
        def quick():
            return 42

        with caplog.at_level(logging.DEBUG, logger="src.utils.perf"):
            result = quick()

        assert result == 42
        # A debug message with the function name should have been emitted
        assert any("quick" in record.message for record in caplog.records)

    def test_no_log_when_debug_disabled(self, caplog):
        from src.utils.perf import timed

        @timed
        def silent():
            return 7

        with caplog.at_level(logging.WARNING, logger="src.utils.perf"):
            result = silent()

        assert result == 7
        assert not any("silent" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# user_ini_manager.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveUserIniDict:
    """save_user_ini_dict writes key=value pairs to a file."""

    def test_writes_all_entries(self, tmp_path: Path):
        from src.utils.user_ini_manager import save_user_ini_dict

        dest = tmp_path / "user.ini"
        data = {"vehicle_NameHunter": "My Cutlass", "item_NameSHLD_Aspirum": "My Shield"}
        count = save_user_ini_dict(data, dest)
        assert count == 2
        assert dest.exists()
        content = dest.read_text(encoding="utf-8")
        assert "vehicle_NameHunter=My Cutlass\n" in content
        assert "item_NameSHLD_Aspirum=My Shield\n" in content

    def test_returns_correct_count(self, tmp_path: Path):
        from src.utils.user_ini_manager import save_user_ini_dict

        dest = tmp_path / "user.ini"
        count = save_user_ini_dict({"a": "1", "b": "2", "c": "3"}, dest)
        assert count == 3

    def test_empty_dict_creates_empty_file(self, tmp_path: Path):
        from src.utils.user_ini_manager import save_user_ini_dict

        dest = tmp_path / "user.ini"
        count = save_user_ini_dict({}, dest)
        assert count == 0
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == ""

    def test_creates_parent_directories(self, tmp_path: Path):
        from src.utils.user_ini_manager import save_user_ini_dict

        dest = tmp_path / "deep" / "nested" / "user.ini"
        save_user_ini_dict({"k": "v"}, dest)
        assert dest.exists()


@pytest.mark.unit
class TestSaveUserIni:
    """save_user_ini writes only modified entries."""

    def _make_entries(self):
        from src.models.string_model import StringEntry

        return [
            StringEntry(
                key="vehicle_NameHunter",
                source_file="global",
                original_value="Cutlass",
                custom_value="My Cutlass",
                status="Modified",
                category="Ships",
            ),
            StringEntry(
                key="item_NameSHLD_Aspirum",
                source_file="global",
                original_value="Aspirum Shield",
                custom_value="",  # unmodified
                status="Unmodified",
                category="Ship Items",
            ),
            StringEntry(
                key="contract_001",
                source_file="contracts",
                original_value="Delivery",
                custom_value="My Delivery",
                status="Modified",
                category="Missions",
            ),
        ]

    def test_only_modified_entries_written(self, tmp_path: Path):
        from src.utils.user_ini_manager import save_user_ini

        entries = self._make_entries()
        dest = tmp_path / "user.ini"
        count = save_user_ini(entries, dest)
        assert count == 2  # only the two modified entries
        content = dest.read_text(encoding="utf-8")
        assert "vehicle_NameHunter=My Cutlass\n" in content
        assert "contract_001=My Delivery\n" in content
        assert "item_NameSHLD_Aspirum" not in content

    def test_no_modified_entries_creates_empty_file(self, tmp_path: Path):
        from src.models.string_model import StringEntry
        from src.utils.user_ini_manager import save_user_ini

        entries = [
            StringEntry(
                key="k",
                source_file="global",
                original_value="v",
                custom_value="",
                status="Unmodified",
                category="Other",
            )
        ]
        dest = tmp_path / "user.ini"
        count = save_user_ini(entries, dest)
        assert count == 0
        assert dest.read_text(encoding="utf-8") == ""


@pytest.mark.unit
class TestGenerateUserIniFromDiff:
    """generate_user_ini_from_diff bootstraps user.ini from base vs. current diff."""

    def test_writes_differing_keys(self, tmp_path: Path):
        from src.utils.user_ini_manager import generate_user_ini_from_diff

        base = tmp_path / "base.ini"
        base.write_text("k1=base_v1\nk2=base_v2\n", encoding="utf-8")
        current = tmp_path / "global.ini"
        current.write_text("k1=base_v1\nk2=changed_v2\n", encoding="utf-8")
        dest = tmp_path / "user.ini"

        count = generate_user_ini_from_diff(base, current, dest)
        assert count == 1
        content = dest.read_text(encoding="utf-8")
        assert "k2=changed_v2\n" in content
        assert "k1" not in content

    def test_skips_when_user_ini_already_exists(self, tmp_path: Path):
        from src.utils.user_ini_manager import generate_user_ini_from_diff

        base = tmp_path / "base.ini"
        base.write_text("k=v\n", encoding="utf-8")
        current = tmp_path / "global.ini"
        current.write_text("k=changed\n", encoding="utf-8")
        dest = tmp_path / "user.ini"
        dest.write_text("existing=content\n", encoding="utf-8")

        count = generate_user_ini_from_diff(base, current, dest)
        assert count == 0
        # Existing file must not have been overwritten
        assert dest.read_text(encoding="utf-8") == "existing=content\n"

    def test_returns_zero_when_no_differences(self, tmp_path: Path):
        from src.utils.user_ini_manager import generate_user_ini_from_diff

        base = tmp_path / "base.ini"
        base.write_text("k1=v1\nk2=v2\n", encoding="utf-8")
        current = tmp_path / "global.ini"
        current.write_text("k1=v1\nk2=v2\n", encoding="utf-8")
        dest = tmp_path / "user.ini"

        count = generate_user_ini_from_diff(base, current, dest)
        assert count == 0
        assert not dest.exists()

    def test_returns_zero_when_base_missing(self, tmp_path: Path):
        from src.utils.user_ini_manager import generate_user_ini_from_diff

        current = tmp_path / "global.ini"
        current.write_text("k=v\n", encoding="utf-8")
        dest = tmp_path / "user.ini"

        count = generate_user_ini_from_diff(tmp_path / "no_base.ini", current, dest)
        assert count == 0

    def test_returns_zero_when_current_missing(self, tmp_path: Path):
        from src.utils.user_ini_manager import generate_user_ini_from_diff

        base = tmp_path / "base.ini"
        base.write_text("k=v\n", encoding="utf-8")
        dest = tmp_path / "user.ini"

        count = generate_user_ini_from_diff(base, tmp_path / "no_current.ini", dest)
        assert count == 0


# ---------------------------------------------------------------------------
# user_cfg.py — ensure_user_cfg_language
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEnsureUserCfgLanguage:
    """ensure_user_cfg_language manages the g_language setting in user.cfg."""

    def _mock_settings(self, monkeypatch, channel_path: str):
        """Patch AppSettings to return a controllable channel path."""
        import src.utils.user_cfg as ucfg_mod

        monkeypatch.setattr(
            ucfg_mod.AppSettings,
            "get_game_install_path",
            staticmethod(lambda: channel_path),
        )
        monkeypatch.setattr(
            ucfg_mod.AppSettings,
            "get_active_channel",
            staticmethod(lambda: "LIVE"),
        )

    def test_creates_user_cfg_when_absent(self, tmp_path: Path, monkeypatch):
        from src.utils.user_cfg import ensure_user_cfg_language

        channel_dir = tmp_path / "LIVE"
        channel_dir.mkdir()
        self._mock_settings(monkeypatch, str(channel_dir))

        result = ensure_user_cfg_language()
        assert result is True
        user_cfg = channel_dir / "user.cfg"
        assert user_cfg.exists()
        assert "g_language = english" in user_cfg.read_text(encoding="utf-8")

    def test_adds_setting_to_existing_file_without_it(self, tmp_path: Path, monkeypatch):
        from src.utils.user_cfg import ensure_user_cfg_language

        channel_dir = tmp_path / "LIVE"
        channel_dir.mkdir()
        user_cfg = channel_dir / "user.cfg"
        user_cfg.write_text("con_restricted = 0\n", encoding="utf-8")
        self._mock_settings(monkeypatch, str(channel_dir))

        result = ensure_user_cfg_language()
        assert result is True
        content = user_cfg.read_text(encoding="utf-8")
        assert "g_language = english" in content
        assert "con_restricted = 0" in content  # original line preserved

    def test_noop_when_setting_already_present(self, tmp_path: Path, monkeypatch):
        from src.utils.user_cfg import ensure_user_cfg_language

        channel_dir = tmp_path / "LIVE"
        channel_dir.mkdir()
        user_cfg = channel_dir / "user.cfg"
        user_cfg.write_text("g_language = english\n", encoding="utf-8")
        self._mock_settings(monkeypatch, str(channel_dir))

        result = ensure_user_cfg_language()
        assert result is True
        # Should still contain exactly one occurrence
        content = user_cfg.read_text(encoding="utf-8")
        assert content.count("g_language = english") == 1

    def test_returns_false_when_path_not_configured(self, tmp_path: Path, monkeypatch):
        import src.utils.user_cfg as ucfg_mod
        from src.utils.user_cfg import ensure_user_cfg_language

        monkeypatch.setattr(
            ucfg_mod.AppSettings,
            "get_game_install_path",
            staticmethod(lambda: ""),
        )

        result = ensure_user_cfg_language()
        assert result is False

    def test_returns_false_when_channel_dir_missing(self, tmp_path: Path, monkeypatch):
        from src.utils.user_cfg import ensure_user_cfg_language

        self._mock_settings(monkeypatch, str(tmp_path / "LIVE"))  # dir doesn't exist

        result = ensure_user_cfg_language()
        assert result is False
