import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import QTableView
from src.gui.filter_header import FilterHeaderView
from src.gui.string_table_model import HEADER_LABELS

pytestmark = pytest.mark.unit


@pytest.fixture
def header(qtbot):
    table = QTableView()
    qtbot.addWidget(table)
    table.setModel(QStandardItemModel(1, 7, table))
    header = FilterHeaderView(HEADER_LABELS, table, choice_columns={0, 4, 6})
    table.setHorizontalHeader(header)
    table.resize(1000, 400)
    table.show()
    yield header


def test_all_columns_have_accessible_filters(header):
    assert all(editor is not None for editor in header._filters)
    assert all(editor.accessibleName() for editor in header._filters)
    assert header.get_filter_texts() == [""] * 7


def test_choices_and_modes(header, qtbot):
    header.set_filter_choices(0, ["Ships", "Missions"])
    header.set_filter_choices(6, ["Modified", "Enhanced"])
    with qtbot.waitSignal(header.filter_changed):
        header._filters[0].setCurrentIndex(1)
        header._filters[1].setText("Vehicle_")
        header._modes[1].setCurrentIndex(2)
        header._filters[4].setCurrentIndex(2)
        header._filters[6].setCurrentIndex(1)
    assert header.get_filter_texts() == ["ships", "vehicle_", "", "", "★", "", "modified"]
    assert header.get_filter_modes() == [
        "exact",
        "starts_with",
        "contains",
        "contains",
        "excludes",
        "contains",
        "exact",
    ]


def test_refresh_choices_preserves_selection(header):
    header.set_filter_choices(0, ["Ships", "Missions"])
    header._filters[0].setCurrentIndex(1)
    header.set_filter_choices(0, ["Commodities", "Ships"])
    assert header.get_filter_texts()[0] == "ships"
    header.set_filter_choices(0, ["Missions"])
    assert header.get_filter_texts()[0] == ""


def test_clear_all_resets_text_modes_and_choices_once(header):
    header._filters[1].setText("example")
    header._modes[1].setCurrentIndex(3)
    header._filters[4].setCurrentIndex(1)
    calls = []
    header.filter_changed.connect(lambda: calls.append(True))
    header.clear_all()
    assert calls == [True]
    assert not header._debounce.isActive()
    assert header.get_filter_texts() == [""] * 7
    assert header.get_filter_modes()[1] == "contains"


def test_filter_geometry_tracks_resize_and_move(header):
    header.resizeSection(1, 190)
    assert header._controls[1].width() == 190
    header.setSectionsMovable(True)
    header.moveSection(1, 2)
    assert header._controls[1].x() == header.sectionPosition(1) - header.offset()


def test_filters_are_keyboard_accessible(header, qtbot):
    editor = header._filters[1]
    editor.setFocus()
    qtbot.keyClicks(editor, "example")
    assert header.get_filter_texts()[1] == "example"
    assert editor.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_pending_filter_timer_is_safe_when_header_is_destroyed(qtbot):
    from PyQt6 import sip

    table = QTableView()
    table.setModel(QStandardItemModel(1, 7, table))
    header = FilterHeaderView(HEADER_LABELS, table, choice_columns={0, 4, 6})
    table.setHorizontalHeader(header)
    header._filters[1].setText("pending")
    assert header._debounce.isActive()
    sip.delete(table)
    qtbot.wait(350)
