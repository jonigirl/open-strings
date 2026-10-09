"""Log tab — in-app log viewer with export capability."""

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

# Maximum lines kept in the viewer before oldest lines are dropped
_MAX_LINES = 2000
_POPOUT_SIZE = (960, 600)

# Colours per level
_LEVEL_COLORS = {
    logging.DEBUG: "#888888",
    logging.INFO: "#cccccc",
    logging.WARNING: "#ff9800",
    logging.ERROR: "#f44336",
    logging.CRITICAL: "#f44336",
}

_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class _LogEmitter(QObject):
    """Bridge between the stdlib logging system and Qt signals.

    Lives on the main thread; the handler posts records to it via a signal
    so Qt's event loop delivers them safely regardless of which thread logs.
    """

    record_emitted = pyqtSignal(str, int)  # formatted message, levelno


class _QtLogHandler(logging.Handler):
    """logging.Handler that forwards records to a _LogEmitter signal."""

    def __init__(self, emitter: _LogEmitter):
        super().__init__()
        self._emitter = emitter

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._emitter.record_emitted.emit(msg, record.levelno)
        except Exception:
            self.handleError(record)


class LogTab(QWidget):
    """Tab showing a live stream of application log output."""

    def __init__(self):
        super().__init__()
        self._line_count = 0
        self._popout: QDialog | None = None
        self._emitter = _LogEmitter()
        self._handler = _QtLogHandler(self._emitter)
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", datefmt="%H:%M:%S")
        )
        self._emitter.record_emitted.connect(self._append_record)
        self.setup_ui()
        self._install_handler()

    # ── UI ────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        self._tab_layout = QVBoxLayout(self)
        self._tab_layout.setContentsMargins(0, 0, 0, 0)
        self._content = QWidget(self)
        self._tab_layout.addWidget(self._content)
        self._return_btn = QPushButton("Return Log to Tab", self)
        self._return_btn.clicked.connect(self._return_to_tab)
        self._return_btn.hide()
        self._tab_layout.addWidget(self._return_btn)
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar row
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Min level:"))
        self._level_combo = QComboBox()
        self._level_combo.setToolTip(
            "Minimum severity to display. Entries below the selected level are hidden (DEBUG < INFO < WARNING < ERROR)."
        )
        for level, name in [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
        ]:
            self._level_combo.addItem(name, userData=level)
        self._level_combo.setCurrentIndex(1)  # default: INFO
        self._level_combo.currentIndexChanged.connect(self._on_level_changed)
        toolbar.addWidget(self._level_combo)

        toolbar.addSpacing(16)

        self._autoscroll_cb = QCheckBox("Auto-scroll")
        self._autoscroll_cb.setToolTip(
            "Automatically scroll to the newest log entry as it arrives. Turn off to pin the view while inspecting older lines."
        )
        self._autoscroll_cb.setChecked(True)
        toolbar.addWidget(self._autoscroll_cb)

        toolbar.addStretch()

        self._popout_btn = QPushButton("Pop Out")
        self._popout_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self._popout_btn.setToolTip("Move the live log into a separate window")
        self._popout_btn.clicked.connect(self._toggle_popout)
        toolbar.addWidget(self._popout_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setMaximumWidth(70)
        clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(clear_btn)

        export_btn = QPushButton("Export to file…")
        export_btn.setMaximumWidth(130)
        export_btn.clicked.connect(self._export)
        toolbar.addWidget(export_btn)

        layout.addLayout(toolbar)

        # Log viewer
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(_MAX_LINES)
        self._view.setFont(QFont("Consolas", 11))
        self._view.setAccessibleName("Application log")
        self._view.setStyleSheet("QPlainTextEdit { background: #1e1e1e; color: #cccccc; border: none; }")
        # Disable the default word-wrap so long lines scroll horizontally
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._view)

        # Status bar
        self._status_label = QLabel("0 lines")
        self._status_label.setProperty("role", "secondary")
        layout.addWidget(self._status_label)

    def _toggle_popout(self):
        if self._popout is not None:
            self._return_to_tab()
            return
        self._popout = QDialog(self)
        self._popout.setWindowTitle("Open Strings - Log")
        self._popout.resize(*_POPOUT_SIZE)
        self._popout.finished.connect(self._restore_log)
        layout = QVBoxLayout(self._popout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content)
        self._return_btn.show()
        self._popout_btn.setText("Return to Tab")
        self._popout_btn.setToolTip("Return the live log to its tab")
        self._popout.show()
        self._view.setFocus()

    def _return_to_tab(self):
        if self._popout is not None:
            self._popout.close()

    def _restore_log(self):
        popout = self._popout
        self._popout = None
        self._tab_layout.insertWidget(0, self._content)
        self._content.show()
        self._return_btn.hide()
        self._popout_btn.setText("Pop Out")
        self._popout_btn.setToolTip("Move the live log into a separate window")
        self._popout_btn.setFocus()
        if popout is not None:
            popout.deleteLater()

    # ── Handler lifecycle ─────────────────────────────────────────────────────

    def _install_handler(self):
        root = logging.getLogger()
        self._on_level_changed()  # sync handler level with combo
        root.addHandler(self._handler)

    def remove_handler(self):
        """Call on app close to avoid logging to a destroyed widget."""
        logging.getLogger().removeHandler(self._handler)
        self._return_to_tab()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_level_changed(self):
        level = self._level_combo.currentData()
        if level is not None:
            self._handler.setLevel(level)

    def _append_record(self, msg: str, levelno: int):
        color = _LEVEL_COLORS.get(levelno, "#cccccc")
        bold = levelno >= logging.ERROR

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)

        cursor = self._view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(msg + "\n", fmt)

        if (doc := self._view.document()) is not None:
            self._line_count = doc.blockCount()
        self._status_label.setText(f"{self._line_count} lines")

        if self._autoscroll_cb.isChecked():
            self._view.setTextCursor(cursor)
            self._view.ensureCursorVisible()

    def _clear(self):
        self._view.clear()
        self._line_count = 0
        self._status_label.setText("0 lines")

    def _export(self):
        default_name = f"open_strings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export log", default_name, "Log files (*.log);;Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self._view.toPlainText(), encoding="utf-8")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Export failed", str(e))
