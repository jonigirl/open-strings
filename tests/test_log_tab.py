import logging

import pytest
from PyQt6.QtCore import Qt
from src.gui.log_tab import LogTab

pytestmark = pytest.mark.unit


@pytest.fixture
def log_tab(qtbot):
    tab = LogTab()
    qtbot.addWidget(tab)
    tab.show()
    yield tab
    tab.remove_handler()


def test_popout_preserves_buffer_and_handler(log_tab, qtbot):
    log_tab._append_record("before detach", logging.INFO)
    handler_count = logging.getLogger().handlers.count(log_tab._handler)
    qtbot.mouseClick(log_tab._popout_btn, Qt.MouseButton.LeftButton)
    popout = log_tab._popout
    assert popout is not None
    assert not popout.isModal()
    assert log_tab._content.parent() is popout
    record = logging.LogRecord("test", logging.INFO, "", 0, "while detached", (), None)
    log_tab._handler.emit(record)
    qtbot.waitUntil(lambda: "while detached" in log_tab._view.toPlainText())
    popout.close()
    assert log_tab._popout is None
    assert log_tab._content.parent() is log_tab
    assert "before detach" in log_tab._view.toPlainText()
    assert log_tab._view.toPlainText().count("while detached") == 1
    assert logging.getLogger().handlers.count(log_tab._handler) == handler_count


def test_return_button_and_repeated_detach(log_tab, qtbot):
    for _ in range(2):
        log_tab._toggle_popout()
        qtbot.mouseClick(log_tab._return_btn, Qt.MouseButton.LeftButton)
        assert log_tab._popout is None
        assert log_tab._content.parent() is log_tab


def test_cleanup_closes_detached_window(log_tab):
    log_tab._toggle_popout()
    popout = log_tab._popout
    log_tab.remove_handler()
    assert not popout.isVisible()
    assert log_tab._handler not in logging.getLogger().handlers


def test_popout_button_returns_to_tab(log_tab, qtbot):
    log_tab._toggle_popout()
    qtbot.mouseClick(log_tab._popout_btn, Qt.MouseButton.LeftButton)
    assert log_tab._popout is None
