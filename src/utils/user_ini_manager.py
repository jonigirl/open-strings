"""User INI persistence and import utilities."""

import logging
from pathlib import Path

from src.models.string_model import StringEntry
from src.parser.ini_parser import parse_ini_file
from src.utils.perf import timed

logger = logging.getLogger(__name__)


def _write_kv_to_path(data: dict[str, str], path: Path) -> int:
    """Write key=value pairs to *path*. Returns the number of entries written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for key, value in data.items():
                f.write(f"{key}={value}\n")
        return len(data)
    except Exception as e:
        logger.error(f"Failed to save {path}: {e}")
        raise


def should_autosave_user_ini(entries: list[StringEntry], user_ini_path: Path) -> bool:
    """Return False when writing would replace non-empty on-disk content with nothing.

    Prevents wiping persisted edits when the app is closed before any entry
    has been modified in this session (e.g. instant-exit during background load).

    Returns True in all other cases:
    - Any entry is modified → write (real edits to persist)
    - user.ini doesn't exist → write (nothing to lose)
    - user.ini is empty/zero-size → write (already blank, safe)
    """
    if any(e.is_modified for e in entries):
        return True
    try:
        size = user_ini_path.stat().st_size
    except FileNotFoundError:
        return True
    if size > 0:
        logger.warning(
            "Skipping autosave: no modified entries but %s has %d bytes — "
            "avoiding overwrite of pre-existing user edits",
            user_ini_path,
            size,
        )
        return False
    return True


@timed
def save_user_ini(entries: list[StringEntry], user_ini_path: Path) -> int:
    """Write only user-modified entries to user.ini.

    Args:
        entries: List of StringEntry objects from self.entries
        user_ini_path: Destination path for user.ini

    Returns:
        Number of entries written

    Raises:
        IOError: If write fails
    """
    user_edits = {entry.key: entry.custom_value for entry in entries if entry.is_modified}
    count = _write_kv_to_path(user_edits, user_ini_path)
    logger.info(f"Saved {count} user edits to {user_ini_path}")
    return count


@timed
def save_user_ini_dict(data: dict[str, str], user_ini_path: Path) -> int:
    """Write a raw key-value dict to user.ini.

    Used by the import flow where we have a pre-merged dict rather than
    StringEntry objects.

    Args:
        data: Dict of key → value pairs to write
        user_ini_path: Destination path for user.ini

    Returns:
        Number of entries written
    """
    count = _write_kv_to_path(data, user_ini_path)
    logger.info(f"Saved {count} entries to {user_ini_path}")
    return count


@timed
def generate_user_ini_from_diff(reference_path: Path, current_path: Path, user_ini_path: Path) -> int:
    """Diff reference vs current file, write differing keys as user.ini.

    Used on first run to bootstrap user edits from existing game file.

    Args:
        reference_path: Path to reference base file (base.ini)
        current_path: Path to current game file (global.ini)
        user_ini_path: Destination path for user.ini

    Returns:
        Number of entries written, or 0 if skipped (missing files, etc.)
    """
    if not reference_path.exists():
        logger.debug(f"Reference file not found: {reference_path}")
        return 0

    if not current_path.exists():
        logger.debug(f"Current file not found: {current_path}")
        return 0

    if user_ini_path.exists():
        logger.debug(f"user.ini already exists: {user_ini_path}")
        return 0

    try:
        reference = parse_ini_file(reference_path)
        current = parse_ini_file(current_path)

        diffs = {}
        for key, current_value in current.items():
            reference_value = reference.get(key, "")
            if current_value != reference_value:
                diffs[key] = current_value

        if not diffs:
            logger.info("No differences found between reference and current file")
            return 0

        count = _write_kv_to_path(diffs, user_ini_path)
        logger.info(f"Bootstrapped {count} user edits from diff")
        return count

    except Exception as e:
        logger.warning(f"Failed to generate user.ini from diff: {e}")
        return 0
