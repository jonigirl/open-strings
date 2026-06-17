"""Guided-tour lifecycle — owns the TutorialTour instance and first-run logic.

Extracted from MainWindow so tour setup can be tested independently.  The
*post-tour startup tasks* (source sync + update check) remain in MainWindow
because they call into ``worker_coord`` and ``update_mgr`` — this manager
signals when the tour is done and MainWindow handles the rest.

Signals
-------
tour_finished
    Emitted when:
    - The tour completed or was skipped (both paths record the version).
    - No tour was required (already seen current version) — fired immediately
      via a zero-delay timer so the caller always gets exactly one signal
      per ``maybe_start_first_run()`` invocation.
    - The tour threw an exception on launch — startup tasks must still run.

Usage::

    self.tutorial_mgr = TutorialManager(self)
    self.tutorial_mgr.tour_finished.connect(self._start_post_tutorial_tasks)
    # hook from showEvent:
    self.tutorial_mgr.maybe_start_first_run()
    # toolbar button replay:
    self.tutorial_mgr.start_tutorial()
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from src.gui.coach_mark import CoachMarkStep, TutorialTour
from src.utils.resource import get_resource_path
from src.utils.settings import AppSettings
from src.utils.version import get_version

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow

logger = logging.getLogger(__name__)


class TutorialManager(QObject):
    """Manages the guided-tour lifecycle for MainWindow."""

    tour_finished = pyqtSignal()

    def __init__(self, parent: QMainWindow) -> None:  # type: ignore[override]
        super().__init__(parent)
        self._parent = parent
        self._tour: TutorialTour | None = None
        self._first_run_checked: bool = False

    # ── Public API ────────────────────────────────────────────────────────

    def maybe_start_first_run(self) -> None:
        """Auto-start the tour on first launch of an unseen version.

        Called from ``MainWindow.showEvent`` — safe to call multiple times;
        subsequent calls after the first are no-ops.

        Emits :attr:`tour_finished` (via ``QTimer.singleShot(0, ...)`` for the
        no-tour branch so callers don't need two paths) or fires after the
        tour completes.
        """
        if self._first_run_checked:
            return
        self._first_run_checked = True

        last_seen = AppSettings.get_tutorial_completed_version()
        current = get_version()
        if last_seen == current:
            QTimer.singleShot(0, self.tour_finished.emit)
            return
        QTimer.singleShot(400, self.start_tutorial)

    def start_tutorial(self) -> None:
        """Launch the guided tour.  Safe to call while a tour is running
        (the second call is silently ignored).
        """
        if self._tour is not None and self._tour.is_running():
            return
        try:
            self._tour = TutorialTour(self._parent, self._build_tour_steps())
            self._tour.finished.connect(self._on_tour_done)
            self._tour.start()
        except Exception:
            logger.exception("Tutorial failed to launch; firing post-tour tasks anyway")
            self._tour = None
            self.tour_finished.emit()

    # ── Internal ──────────────────────────────────────────────────────────

    @pyqtSlot(bool)
    def _on_tour_done(self, completed: bool) -> None:
        AppSettings.set_tutorial_completed_version(get_version())
        self._tour = None
        self.tour_finished.emit()

    def _tour_step_wiring(self) -> dict[str, dict]:
        """Map step ids to widget targets and pre-actions.

        Closures capture ``self._parent`` so the full wiring lives here while
        widgets still live on the window.
        """
        p = self._parent

        def _switch_to(tab_index: int):
            def _action():
                if hasattr(p, "tabs"):
                    p.tabs.setCurrentIndex(tab_index)

            return _action

        strings_tab = getattr(p, "_strings_tab_index", 0)
        config_tab = getattr(p, "_config_tab_index", 1)
        enh_tab = getattr(p, "_enhancements_tab_index", 2)

        return {
            "welcome": {"target": lambda: None, "pre_action": None},
            "extract": {"target": lambda: p.config_tab._extract_btn, "pre_action": _switch_to(config_tab)},
            "edit": {"target": lambda: p.table, "pre_action": _switch_to(strings_tab)},
            "preview": {"target": lambda: p.preview_pane, "pre_action": _switch_to(strings_tab)},
            "apply": {"target": lambda: p.apply_btn, "pre_action": None},
            "enhancements": {
                "target": lambda: p.enhancements_tab._generate_enhancements_btn,
                "pre_action": _switch_to(enh_tab),
            },
            "help": {"target": lambda: p.help_btn, "pre_action": _switch_to(strings_tab)},
        }

    def _build_tour_steps(self) -> list[CoachMarkStep]:
        """Assemble the tour by combining ``assets/tutorial.json`` with wiring."""
        wiring = self._tour_step_wiring()

        try:
            path = Path(get_resource_path("assets/tutorial.json"))
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Could not load assets/tutorial.json: {e} — tour disabled")
            return []

        steps: list[CoachMarkStep] = []
        for raw in payload.get("steps", []):
            step_id = raw.get("id")
            if not step_id:
                logger.warning(f"Tutorial step missing 'id'; skipped: {raw!r}")
                continue
            w = wiring.get(step_id)
            if w is None:
                logger.warning(f"Tutorial step {step_id!r} has no wiring; skipped")
                continue
            title = raw.get("title", "")
            description = raw.get("description", "")
            if not title or not description:
                logger.warning(f"Tutorial step {step_id!r} missing title/description; skipped")
                continue
            steps.append(
                CoachMarkStep(
                    target=w["target"],
                    title=title,
                    description=description,
                    pre_action=w.get("pre_action"),
                    preferred_side=raw.get("preferred_side", "auto"),
                )
            )
        return steps
