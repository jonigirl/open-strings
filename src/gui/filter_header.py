"""Per-column filter header for the strings table."""

from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHeaderView, QLineEdit, QVBoxLayout, QWidget

from src.gui.string_table_model import COL_STAR

_MATCH_OPTIONS = (
    ("Contains", "contains"),
    ("Exact", "exact"),
    ("Starts with", "starts_with"),
    ("Excludes", "excludes"),
)
_FILTER_CONTROL_HEIGHT = 30


class FilterHeaderView(QHeaderView):
    """Column filters with text matching modes and discrete-value selectors."""

    filter_changed = pyqtSignal()

    FILTER_ROW_HEIGHT = _FILTER_CONTROL_HEIGHT * 2 + 4

    def __init__(
        self,
        column_names: list[str],
        parent=None,
        skip_columns: set[int] | None = None,
        choice_columns: set[int] | None = None,
    ):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setSectionsClickable(True)
        self._column_names = column_names
        self._skip_columns = skip_columns or set()
        self._filters: list[QLineEdit | QComboBox | None] = []
        self._controls: list[QWidget | None] = []
        self._modes: list[QComboBox | None] = []
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.filter_changed)

        for i, name in enumerate(column_names):
            if i in self._skip_columns:
                self._filters.append(None)
                self._controls.append(None)
                self._modes.append(None)
                continue
            panel = QWidget(self)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(2, 0, 2, 0)
            layout.setSpacing(4)
            mode = None
            if i in (choice_columns or set()):
                editor = QComboBox(panel)
                if i == COL_STAR:
                    editor.addItem("All", ("", "contains"))
                    editor.addItem("Yes", ("★", "exact"))
                    editor.addItem("No", ("★", "excludes"))
                else:
                    editor.addItem("All", "")
                editor.currentIndexChanged.connect(self._on_text_changed)
                layout.addStretch()
            else:
                mode = QComboBox(panel)
                for label, value in _MATCH_OPTIONS:
                    mode.addItem(label, value)
                mode.setAccessibleName(f"{name} match mode")
                mode.setToolTip(f"Match mode for {name}")
                mode.setMinimumHeight(_FILTER_CONTROL_HEIGHT)
                mode.currentIndexChanged.connect(self._on_text_changed)
                layout.addWidget(mode)
                editor = QLineEdit(panel)
                editor.setPlaceholderText("Filter...")
                editor.setClearButtonEnabled(True)
                editor.textChanged.connect(self._on_text_changed)
            editor.setMinimumHeight(_FILTER_CONTROL_HEIGHT)
            editor.setAccessibleName(f"{name} filter")
            editor.setToolTip(f"Filter {name}")
            layout.addWidget(editor)
            self._filters.append(editor)
            self._controls.append(panel)
            self._modes.append(mode)
        self.sectionResized.connect(self._position_editors)
        self.sectionMoved.connect(self._position_editors)

    def set_filter_choices(self, column: int, choices: list[str]):
        editor = self._filters[column]
        if not isinstance(editor, QComboBox) or column == COL_STAR:
            return
        previous = editor.currentData()
        editor.blockSignals(True)
        editor.clear()
        editor.addItem("All", "")
        for choice in choices:
            editor.addItem(choice, choice.lower())
        editor.setCurrentIndex(max(0, editor.findData(previous)))
        editor.blockSignals(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_filter_texts(self) -> list[str]:
        """Return lowered text for each column filter (empty string for skipped columns)."""
        texts = []
        for column, editor in enumerate(self._filters):
            if isinstance(editor, QLineEdit):
                texts.append(editor.text().lower())
            elif isinstance(editor, QComboBox):
                value = editor.currentData()
                texts.append(value[0] if column == COL_STAR else value)
            else:
                texts.append("")
        return texts

    def get_filter_modes(self) -> list[str]:
        modes = []
        for column, editor in enumerate(self._filters):
            mode = self._modes[column]
            if mode is not None:
                modes.append(mode.currentData())
            elif isinstance(editor, QComboBox):
                modes.append(editor.currentData()[1] if column == COL_STAR else "exact")
            else:
                modes.append("contains")
        return modes

    def clear_all(self):
        """Clear every filter input without triggering per-keystroke signals."""
        self._debounce.stop()
        for editor in self._filters + self._modes:
            if editor is None:
                continue
            editor.blockSignals(True)
            if isinstance(editor, QComboBox):
                editor.setCurrentIndex(0)
            else:
                editor.clear()
            editor.blockSignals(False)
        self.filter_changed.emit()

    # ------------------------------------------------------------------
    # Size / paint
    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        return QSize(s.width(), s.height() + self.FILTER_ROW_HEIGHT)

    def sectionSizeFromContents(self, logicalIndex: int) -> QSize:
        size = super().sectionSizeFromContents(logicalIndex)
        if logicalIndex < len(self._controls) and (panel := self._controls[logicalIndex]) is not None:
            size.setWidth(max(size.width(), panel.sizeHint().width()))
        return size

    def paintSection(self, painter, rect, logicalIndex):
        """Paint the header label in the top portion only, not centered over the full height."""
        # During transient layout passes (theme swap, dock toggle, splitter drag,
        # font load), rect.height() can momentarily collapse below base_h. The
        # previous min(rect.height(), base_h) clamp then painted the label into
        # a near-zero rect, and that paint stuck until a full re-layout — which
        # for users meant restarting the app to get header text back. Force the
        # full base_h here; Qt clips on its own if rect is genuinely smaller.
        base_h = super().sizeHint().height()
        top_rect = QRect(rect.x(), rect.y(), rect.width(), base_h)
        super().paintSection(painter, top_rect, logicalIndex)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def updateGeometries(self):
        super().updateGeometries()
        # Reserve space below the header labels for the filter row
        self.setViewportMargins(0, 0, 0, self.FILTER_ROW_HEIGHT)
        self._position_editors()

    def _position_editors(self):
        """Align each QLineEdit to its column's current geometry."""
        # Editors sit just below the painted header labels.
        # With viewport margins, the base sizeHint gives the label-only height.
        y = super().sizeHint().height()
        for i, panel in enumerate(self._controls):
            if panel is None:
                continue
            x = self.sectionPosition(i) - self.offset()
            w = self.sectionSize(i)
            panel.setGeometry(x, y, w, self.FILTER_ROW_HEIGHT)
            panel.setVisible(not self.isSectionHidden(i))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        """Route clicks in the label area to sorting, let filter row clicks pass through."""
        label_height = self.sizeHint().height() - self.FILTER_ROW_HEIGHT
        if event.position().y() < label_height:
            # Check if a QLineEdit is stealing this click (shouldn't, but just in case)
            super().mousePressEvent(event)
        # Clicks in the filter row are handled by the QLineEdit widgets

    def mouseReleaseEvent(self, event):
        label_height = self.sizeHint().height() - self.FILTER_ROW_HEIGHT
        if event.position().y() < label_height:
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        label_height = self.sizeHint().height() - self.FILTER_ROW_HEIGHT
        if event.position().y() < label_height:
            super().mouseMoveEvent(event)

    def _on_text_changed(self):
        self._debounce.stop()
        self._debounce.start()
