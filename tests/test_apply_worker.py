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


def _worker(tmp_path: Path, entries: list[StringEntry]) -> tuple[ApplyWorker, Path, Path, Path]:
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
    worker = ApplyWorker(entries, target, backups, cache, user_ini, False, 5)
    return worker, base_file, target, user_ini


def test_apply_worker_writes_valid_file_and_preserves_backup(tmp_path, monkeypatch, qtbot):
    worker, base_file, target, user_ini = _worker(tmp_path, [_entry()])
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


def test_declining_missing_source_warning_does_not_apply(tmp_path, monkeypatch, qtbot):
    worker, base_file, target, _user_ini = _worker(tmp_path, [_entry()])
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
