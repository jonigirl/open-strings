from __future__ import annotations

import pytest
from src.gui.enhancements_tab import EnhancementsTab
from src.utils.settings import AppSettings

pytestmark = pytest.mark.unit


@pytest.fixture
def tab(qtbot, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(AppSettings, "get_cache_dir", staticmethod(lambda: cache))
    monkeypatch.setattr(AppSettings, "get_favorite_prefix", staticmethod(lambda: "*"))
    monkeypatch.setattr(AppSettings, "get_enhancement_category_enabled", staticmethod(lambda _key: True))
    widget = EnhancementsTab()
    qtbot.addWidget(widget)
    yield widget, cache


def test_enhancement_cache_status_is_visible_and_accessible(tab):
    widget, cache = tab
    key = next(iter(widget._enhancements_status_labels))
    filename = widget._files_for_category(key)[0]
    (cache / filename).write_text("key=value", encoding="utf-8")

    widget.refresh_enhancements_status()

    status = widget._enhancements_status_labels[key]
    assert status.text() == "Ready"
    assert status.accessibleName()
    assert status.accessibleDescription() == "Enhancement files ready"
    assert widget._enhancements_checkboxes[key].text() in status.toolTip()


def test_missing_enhancement_files_have_textual_status(tab):
    widget, _cache = tab
    key = next(iter(widget._enhancements_status_labels))

    widget.refresh_enhancements_status()

    assert widget._enhancements_status_labels[key].text() == "Missing"


def test_disabled_enhancement_category_reports_off(tab, monkeypatch):
    widget, _cache = tab
    key = next(iter(widget._enhancements_status_labels))
    monkeypatch.setattr(AppSettings, "get_enhancement_category_enabled", staticmethod(lambda _key: False))

    widget.refresh_enhancements_status()

    status = widget._enhancements_status_labels[key]
    assert status.text() == "Off"
    assert status.accessibleDescription() == "Enhancement files off"
