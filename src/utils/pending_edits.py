"""Helpers for preserving and restoring in-memory user edits across reloads.

When a file-loading pass rebuilds ``entries`` from disk sources, any edits the
user has made but not yet *Applied* would be silently dropped — because disk
only knows what was last saved to ``user.ini``.  These functions implement the
snapshot → reload → restore cycle used by every reload path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.string_model import StringEntry


def snapshot_pending_edits(entries: list[StringEntry]) -> dict[str, str]:
    """Return ``{key: custom_value}`` for all entries with a non-empty custom value.

    Captures in-memory edits that may not yet have been written to
    ``user.ini`` — e.g. edits made after the last *Apply* click.  Pass the
    returned snapshot to :func:`restore_pending_edits` after a reload.
    """
    return {e.key: e.custom_value for e in entries if e.custom_value}


def restore_pending_edits(entries: list[StringEntry], snapshot: dict[str, str]) -> int:
    """Re-apply *snapshot* on top of freshly-loaded *entries*.

    Mirrors inline-edit ``setData`` semantics: ``status`` is set to
    ``"Modified"`` when the restored value differs from the new
    ``original_value``, and ``"Unmodified"`` when they match (e.g. the
    game was patched and the new original_value now equals the user's edit).

    Args:
        entries:  Freshly-loaded list to update in-place.
        snapshot: ``{key: custom_value}`` dict from :func:`snapshot_pending_edits`.

    Returns:
        Count of entries that were actually updated.
    """
    if not snapshot:
        return 0
    restored = 0
    for e in entries:
        pending = snapshot.get(e.key)
        if pending is None or pending == e.custom_value:
            continue
        e.custom_value = pending
        e.status = "Modified" if pending != e.original_value else "Unmodified"
        restored += 1
    return restored
