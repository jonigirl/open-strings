import threading
import time

import pytest
from PyQt6.QtCore import Qt
from src.gui import tool_download_dialog
from src.gui.tool_download_dialog import ToolDownloadDialog

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_gateway_error_does_not_show_missing_asset_hint(monkeypatch, code):
    messages = []
    monkeypatch.setattr(tool_download_dialog.QMessageBox, "warning", lambda *args: messages.append(args[2]))

    ToolDownloadDialog._on_error(None, f"HTTP Error {code}: Gateway failure")

    assert len(messages) == 1
    assert "temporarily unavailable" in messages[0]
    assert "HTTP 404" not in messages[0]
    assert "not a compatible replacement" in messages[0]


@pytest.fixture
def blocking_download(monkeypatch):
    started = threading.Event()

    def download(progress_callback=None, cancel_event=None):
        started.set()
        cancel_event.wait(5)
        raise RuntimeError("Download cancelled")

    monkeypatch.setattr(tool_download_dialog, "download_tools", download)
    return started


@pytest.mark.parametrize("trigger", ["cancel_button", "escape"])
def test_cancel_returns_immediately_and_closes_after_worker_stops(qtbot, blocking_download, trigger):
    dialog = ToolDownloadDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    assert blocking_download.wait(2)
    closed: list[bool] = []
    dialog.rejected.connect(lambda: closed.append(True))

    started = time.monotonic()
    if trigger == "escape":
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    else:
        qtbot.mouseClick(dialog._cancel_btn, Qt.MouseButton.LeftButton)
    assert time.monotonic() - started < 0.5

    qtbot.waitUntil(lambda: closed == [True], timeout=3000)
    assert not dialog._worker.isRunning()


def test_repeated_cancel_requests_are_harmless(qtbot, blocking_download):
    dialog = ToolDownloadDialog()
    qtbot.addWidget(dialog)
    assert blocking_download.wait(2)
    with qtbot.waitSignal(dialog.rejected, timeout=3000):
        dialog.reject()
        dialog.reject()
    assert not dialog._worker.isRunning()
