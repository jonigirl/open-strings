from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGroupBox, QPushButton, QScrollArea
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


def test_narrow_enhancements_layout_wraps_descriptions_and_fits_generate_button(tab, qtbot):
    widget, _cache = tab
    widget.resize(376, 512)
    widget.show()
    qtbot.waitUntil(lambda: widget.width() == 376)

    scroll_area = widget.findChild(QScrollArea)
    assert scroll_area is not None
    content = scroll_area.widget()
    assert content is not None
    group = next(group for group in widget.findChildren(QGroupBox) if group.title() == "Localization Enhancements")
    generate = widget._generate_enhancements_btn

    for key, checkbox in widget._enhancements_checkboxes.items():
        status = widget._enhancements_status_labels[key]
        desc = widget._enhancements_description_labels[key]
        for control in (checkbox, status, desc):
            assert control.isVisible()
            assert group.contentsRect().contains(control.geometry())
        assert checkbox.width() >= checkbox.sizeHint().width()
        assert checkbox.geometry().right() < status.geometry().left()
        assert status.geometry().right() < desc.geometry().left()
        assert desc.wordWrap()
        assert desc.heightForWidth(desc.width()) <= desc.height()
    assert any(
        desc.heightForWidth(desc.width()) > desc.fontMetrics().lineSpacing()
        for desc in widget._enhancements_description_labels.values()
    )
    assert generate.text() == "Generate"
    assert generate.width() >= generate.sizeHint().width()
    assert generate.isVisible()
    assert group.contentsRect().contains(generate.geometry())
    assert widget._apply_categories_btn.isVisible()
    assert group.contentsRect().contains(widget._apply_categories_btn.geometry())
    favorites = next(group for group in widget.findChildren(QGroupBox) if group.title() == "Favorites")
    assert favorites.isVisible()
    assert content.rect().contains(favorites.geometry())
    assert widget.favorite_prefix_combo.isVisible()
    assert favorites.contentsRect().contains(widget.favorite_prefix_combo.geometry())
    apply_prefix = next(button for button in favorites.findChildren(QPushButton) if button.text() == "Apply")
    assert apply_prefix.isVisible()
    assert favorites.contentsRect().contains(apply_prefix.geometry())
    assert not widget.favorite_prefix_combo.geometry().intersects(apply_prefix.geometry())
    scrollbar = scroll_area.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    assert favorites.geometry().bottom() <= scrollbar.value() + scroll_area.viewport().height()
