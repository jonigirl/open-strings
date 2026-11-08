from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QMessageBox
from src.gui import main_window

pytestmark = pytest.mark.unit


def test_shared_export_does_not_require_applied_file(monkeypatch, tmp_path):
    class FakeMessageBox:
        ButtonRole = QMessageBox.ButtonRole
        StandardButton = QMessageBox.StandardButton

        def __init__(self, _parent):
            self.buttons = []

        def setWindowTitle(self, _title):
            pass

        def setText(self, _text):
            pass

        def setInformativeText(self, _text):
            pass

        def addButton(self, *_args):
            button = object()
            self.buttons.append(button)
            return button

        def setDefaultButton(self, _button):
            pass

        def exec(self):
            pass

        def clickedButton(self):
            return self.buttons[1]

    dialog_args = []
    output = tmp_path / "shared.zip"
    monkeypatch.setattr(main_window, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(main_window.AppSettings, "get_global_ini_path", staticmethod(lambda: tmp_path / "missing.ini"))
    monkeypatch.setattr(main_window.AppSettings, "get_active_channel", staticmethod(lambda: "PTU"))
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getSaveFileName",
        lambda *args: dialog_args.append(args) or (str(output), ""),
    )
    coordinator = SimpleNamespace(start_locpack_export=Mock())
    window = SimpleNamespace(worker_coord=coordinator)

    main_window.MainWindow.export_locpack(window)

    assert "Shared-LocPack-PTU-" in dialog_args[0][2]
    coordinator.start_locpack_export.assert_called_once_with(output, include_personal_edits=False)
