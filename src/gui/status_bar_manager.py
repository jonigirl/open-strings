"""Status-bar manager — owns all status-bar widgets, the activity spinner,
the channel indicator, and the app-version indicator.

Extracted from MainWindow so the status-bar logic can be tested and
reasoned about independently of the rest of the window.

Usage::

    self.status_bar_mgr = StatusBarManager(self)
    # during setup_ui:
    self.status_bar_mgr.install_widgets()
    # later:
    self.status_bar_mgr.start_spinner()
    self.status_bar_mgr.set_source_status("global", "Global: 4.8.0 ✓")
    self.status_bar_mgr.update_status(self.entries, has_running_worker=self._has_long_running_worker())
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel, QMainWindow, QStatusBar

from src.utils.settings import AppSettings
from src.utils.version import get_version

if TYPE_CHECKING:
    from src.models.string_model import StringEntry

logger = logging.getLogger(__name__)

_SPINNER_FRAMES = ("◐", "◓", "◑", "◒")
_SPINNER_COLORS = ("#5BCEFA", "#F5A9B8", "#5BCEFA", "#F5A9B8")


class StatusBarManager:
    """Owns and manages all permanent status-bar widgets for a QMainWindow.

    The manager is created during MainWindow.__init__ and its widgets are
    installed during setup_ui via :meth:`install_widgets`. After that it
    is the single point of truth for status-bar content updates.
    """

    def __init__(self, parent: QMainWindow) -> None:
        self._parent = parent
        self._source_status: dict[str, str] = {}

        self._spinner_label: QLabel | None = None
        self._spinner_frame: int = 0
        self._spinner_timer: QTimer | None = None

        self._channel_indicator: QLabel | None = None
        self._app_version_indicator: QLabel | None = None

    # ── Internal helpers ──────────────────────────────────────────────────

    def _status_bar(self) -> QStatusBar:
        """Return the parent window's status bar, creating it if needed."""
        status_bar = self._parent.statusBar()
        if status_bar is None:
            status_bar = QStatusBar(self._parent)
            self._parent.setStatusBar(status_bar)
        return status_bar

    # ── Widget installation ───────────────────────────────────────────────

    def install_widgets(self) -> None:
        """Install all permanent status-bar widgets.

        Must be called once during the parent window's setup_ui.  The
        installation order matters: Qt lays out permanent widgets
        left-to-right in addition order, so spinner → app-version →
        channel reads left-to-right across the right side of the bar.
        """
        self._install_spinner()
        self._install_app_version_indicator()
        self._install_channel_indicator()

    def _install_spinner(self) -> None:
        """Install the hidden activity spinner label. Idempotent."""
        if self._spinner_label is not None:
            return
        label = QLabel()
        label.setStyleSheet("font-size: 20px; padding: 0px 4px;")
        label.setVisible(False)
        self._status_bar().addPermanentWidget(label)
        self._spinner_label = label

        timer = QTimer(self._parent)
        timer.setInterval(200)
        timer.timeout.connect(self._tick_spinner)
        self._spinner_timer = timer

    def _install_app_version_indicator(self) -> None:
        """Install a permanent widget showing the app version. Idempotent."""
        if self._app_version_indicator is not None:
            return
        label = QLabel(f"v{get_version()}")
        label.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self._status_bar().addPermanentWidget(label)
        self._app_version_indicator = label

    def _install_channel_indicator(self) -> None:
        """Install a permanent right-side widget showing the active channel. Idempotent."""
        if self._channel_indicator is not None:
            return
        label = QLabel()
        label.setStyleSheet("font-size: 11px; font-weight: bold; padding: 2px 8px;")
        self._status_bar().addPermanentWidget(label)
        self._channel_indicator = label
        self.refresh_channel_indicator()

    # ── Spinner ───────────────────────────────────────────────────────────

    def _tick_spinner(self) -> None:
        if self._spinner_label is None:
            return
        self._spinner_frame = (self._spinner_frame + 1) % len(_SPINNER_FRAMES)
        color = _SPINNER_COLORS[self._spinner_frame]
        self._spinner_label.setStyleSheet(f"font-size: 20px; padding: 0px 4px; color: {color};")
        self._spinner_label.setText(_SPINNER_FRAMES[self._spinner_frame])

    def start_spinner(self) -> None:
        """Show the status-bar activity spinner."""
        if self._spinner_label is None:
            return
        self._spinner_frame = 0
        self._spinner_label.setStyleSheet(f"font-size: 20px; padding: 0px 4px; color: {_SPINNER_COLORS[0]};")
        self._spinner_label.setText(_SPINNER_FRAMES[0])
        self._spinner_label.setVisible(True)
        if self._spinner_timer is not None:
            self._spinner_timer.start()

    def stop_spinner(self) -> None:
        """Hide the status-bar activity spinner."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
        if self._spinner_label is not None:
            self._spinner_label.setVisible(False)

    # ── Channel indicator ─────────────────────────────────────────────────

    def refresh_channel_indicator(self) -> None:
        """Update the channel label to reflect the current active channel."""
        if self._channel_indicator is None:
            return
        self._channel_indicator.setText(f"Channel: {AppSettings.get_active_channel()}")

    # ── Source status & composed message ──────────────────────────────────

    def set_source_status(self, source_name: str, status: str) -> None:
        """Record a sync-status string for *source_name* and refresh the bar.

        Args:
            source_name: Settings key (e.g. ``"global"``, ``"contracts"``).
            status: Human-readable status (e.g. ``"Global: 4.8.0 ✓"``).
        """
        self._source_status[source_name] = status
        self.update_status(entries=None, has_running_worker=False)

    def show_message(self, message: str, timeout: int = 0) -> None:
        """Forward a transient message to the underlying status bar."""
        self._status_bar().showMessage(message, timeout)

    def update_status(
        self,
        entries: list[StringEntry] | None,
        has_running_worker: bool,
    ) -> None:
        """Compose and display the full status-bar message.

        Combines per-source sync statuses, entry / override counts, and the
        active game version + channel suffix.  Suppresses "Ready" fallback
        while a long-running worker is active so progress messages aren't
        clobbered mid-run.

        Args:
            entries: Current loaded entries (may be ``None`` or empty).
            has_running_worker: Pass ``True`` while any worker is running.
        """
        hierarchy = AppSettings.get_merge_hierarchy()
        parts: list[str] = []

        for source_name in hierarchy:
            if source_name in self._source_status:
                parts.append(self._source_status[source_name])

        if entries:
            modified_count = sum(1 for e in entries if e.status in ("Modified", "New"))
            entry_info = f"{len(entries):,} entries"
            if modified_count:
                entry_info += f" | {modified_count} overrides"
            parts.append(entry_info)

        game_version = AppSettings.get_game_version()
        active_channel = AppSettings.get_active_channel()
        if game_version:
            version_parts = game_version.split(".")
            short_version = ".".join(version_parts[:3]) if len(version_parts) >= 3 else game_version
            parts.append(f"SC v{short_version}-{active_channel}")
        elif AppSettings.get_channel_install_path():
            parts.append(f"SC {active_channel} (manifest missing)")

        status_bar = self._status_bar()
        if parts:
            status_bar.showMessage("  |  ".join(parts))
        elif not has_running_worker:
            status_bar.showMessage("Ready")

    # ── Cleanup ───────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Stop the spinner timer. Call from the parent window's closeEvent."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
