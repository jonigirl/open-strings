"""User edits are saved to the user.ini they came from and never leak across channel switches."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.gui.main_window import MainWindow
from src.models.string_model import StringEntry
from src.parser.ini_parser import parse_ini_file
from src.utils.pending_edits import snapshot_pending_edits

pytestmark = pytest.mark.unit


class _FakeWindow:
    _save_user_edits = MainWindow._save_user_edits
    _release_entries_for_switch = MainWindow._release_entries_for_switch

    def __init__(self, entries, user_ini_path):
        self.entries = entries
        self._entries_user_ini_path = user_ini_path
        self._model = MagicMock()
        self._status_bar = MagicMock()


def _entry(key: str, custom: str = "") -> StringEntry:
    return StringEntry(key=key, source_file="global", original_value="stock", custom_value=custom)


def test_cleared_override_is_removed_from_user_ini(tmp_path):
    user_ini = tmp_path / "user.ini"
    user_ini.write_text("a=old\nb=kept\n", encoding="utf-8")
    window = _FakeWindow([_entry("a"), _entry("b", "kept")], user_ini)

    window._save_user_edits()

    assert parse_ini_file(user_ini) == {"b": "kept"}


def test_switch_saves_to_outgoing_user_ini_and_drops_entries(tmp_path):
    live_ini = tmp_path / "LIVE" / "user.ini"
    window = _FakeWindow([_entry("a", "live edit")], live_ini)

    window._release_entries_for_switch()

    assert parse_ini_file(live_ini) == {"a": "live edit"}
    assert window.entries == []
    assert window._entries_user_ini_path is None
    assert snapshot_pending_edits(window.entries) == {}
    window._model.set_data_source.assert_called_once()


def test_save_without_loaded_entries_does_not_write(tmp_path):
    user_ini = tmp_path / "user.ini"
    user_ini.write_text("a=old\n", encoding="utf-8")
    window = _FakeWindow([], user_ini)

    window._save_user_edits()

    assert user_ini.read_text(encoding="utf-8") == "a=old\n"
