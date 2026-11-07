from __future__ import annotations

from pathlib import Path

import pytest
from src.gui.workers import ApplyWorker
from src.models.string_model import StringEntry
from src.utils.settings import AppSettings

pytestmark = pytest.mark.unit


def _entry(key: str = "key", value: str = "custom") -> StringEntry:
    return StringEntry(
        key=key,
        source_file="global",
        original_value="stock",
        custom_value=value,
        status="Modified",
    )


def _worker(tmp_path: Path, entries: list[StringEntry], monkeypatch) -> tuple[ApplyWorker, Path, Path, Path]:
    base_file = tmp_path / "base.ini"
    base_file.write_text("key=stock\n", encoding="utf-8")
    target = tmp_path / "game" / "global.ini"
    target.parent.mkdir()
    target.write_text("key=previous\n", encoding="utf-8")
    backups = tmp_path / "backups"
    backups.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    user_ini = tmp_path / "user.ini"
    user_data_root = tmp_path / "user-data"
    monkeypatch.setattr(AppSettings, "get_active_channel", staticmethod(lambda: "LIVE"))
    monkeypatch.setattr(AppSettings, "get_user_data_dir", staticmethod(lambda: user_data_root))
    worker = ApplyWorker(entries, target, backups, cache, user_ini, False, 5, "LIVE", user_data_root)
    return worker, base_file, target, user_ini


def test_apply_worker_writes_valid_file_and_preserves_backup(tmp_path, monkeypatch, qtbot):
    entries = [_entry()]
    worker, base_file, target, user_ini = _worker(tmp_path, entries, monkeypatch)
    entries[0].custom_value = "changed after click"
    monkeypatch.setattr(
        "src.utils.string_loader.load_sources_from_settings",
        lambda: ({"global": {"key": "stock"}}, ["global"], {}),
    )
    monkeypatch.setattr(AppSettings, "get_source_path", staticmethod(lambda _name: str(base_file)))
    result = []
    worker.completed.connect(lambda success, payload: result.append((success, payload)))

    worker.start()
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    worker.wait()

    success, payload = result[0]
    assert success
    assert target.read_text(encoding="utf-8") == "key=custom\n"
    assert payload["backup_path"].read_text(encoding="utf-8") == "key=previous\n"
    assert user_ini.read_text(encoding="utf-8") == "key=custom\n"


def test_channel_change_during_source_load_aborts_before_writing(tmp_path, monkeypatch, qtbot):
    worker, base_file, target, _user_ini = _worker(tmp_path, [_entry()], monkeypatch)

    def switch_channel_during_load():
        monkeypatch.setattr(AppSettings, "get_active_channel", staticmethod(lambda: "PTU"))
        return ({"global": {"key": "stock"}}, ["global"], {})

    monkeypatch.setattr("src.utils.string_loader.load_sources_from_settings", switch_channel_during_load)
    monkeypatch.setattr(AppSettings, "get_source_path", staticmethod(lambda _name: str(base_file)))
    errors = []
    result = []
    worker.error.connect(errors.append)
    worker.completed.connect(lambda success, payload: result.append((success, payload)))

    worker.start()
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    worker.wait()

    assert not result[0][0]
    assert "channel or data folder changed" in errors[0]
    assert target.read_text(encoding="utf-8") == "key=previous\n"


def test_user_ini_save_failure_rolls_back_game_file(tmp_path, monkeypatch, qtbot):
    worker, base_file, target, _user_ini = _worker(tmp_path, [_entry()], monkeypatch)
    monkeypatch.setattr(
        "src.utils.string_loader.load_sources_from_settings",
        lambda: ({"global": {"key": "stock"}}, ["global"], {}),
    )
    monkeypatch.setattr(AppSettings, "get_source_path", staticmethod(lambda _name: str(base_file)))
    monkeypatch.setattr(
        "src.utils.user_ini_manager.save_user_ini", lambda *_args: (_ for _ in ()).throw(OSError("disk full"))
    )
    errors = []
    result = []
    worker.error.connect(errors.append)
    worker.completed.connect(lambda success, payload: result.append((success, payload)))

    worker.start()
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    worker.wait()

    assert not result[0][0]
    assert "disk full" in errors[0]
    assert target.read_text(encoding="utf-8") == "key=previous\n"


def test_declining_missing_source_warning_does_not_apply(tmp_path, monkeypatch, qtbot):
    worker, base_file, target, _user_ini = _worker(tmp_path, [_entry()], monkeypatch)
    monkeypatch.setattr(
        "src.utils.string_loader.load_sources_from_settings",
        lambda: ({"user": {}}, ["global", "user"], {}),
    )
    monkeypatch.setattr(AppSettings, "get_source_path", staticmethod(lambda _name: str(base_file)))
    monkeypatch.setattr(AppSettings, "is_source_enabled", staticmethod(lambda name: name == "global"))
    missing = []
    result = []
    worker.missing_sources.connect(lambda names: (missing.extend(names), worker.confirm_missing_sources(False)))
    worker.completed.connect(lambda success, payload: result.append((success, payload)))

    worker.start()
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    worker.wait()

    assert missing == ["global"]
    assert result == [(False, {"cancelled": True})]
    assert target.read_text(encoding="utf-8") == "key=previous\n"
