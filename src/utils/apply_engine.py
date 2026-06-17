"""Pure helpers for the Apply-to-Game operation.

These functions contain no Qt dependency and can be tested independently.
``MainWindow.apply_to_game`` is the sole caller.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def create_apply_backup(
    target_path: Path,
    backups_dir: Path,
    max_backups: int,
) -> "Path | None":
    """Copy *target_path* into *backups_dir* and prune the oldest backup if needed.

    Creates the backup before pruning so we never lose a slot when the copy
    fails (e.g. disk full).  Returns the newly created backup path, or
    ``None`` if *target_path* does not exist.
    """
    if not target_path.exists():
        return None

    backup_files = sorted(backups_dir.glob("global.ini.bak_*"), key=lambda f: f.stat().st_mtime)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"global.ini.bak_{timestamp}"
    shutil.copy2(target_path, backup_path)
    logger.info(f"Backed up existing file to {backup_path}")

    if len(backup_files) >= max_backups:
        oldest = backup_files[0]
        try:
            oldest.unlink()
            logger.info(f"Deleted oldest backup: {oldest.name}")
        except OSError as err:
            logger.warning(f"Could not delete oldest backup {oldest.name}: {err}")

    return backup_path


def find_apply_base_file(
    hierarchy: list[str],
    source_paths: dict[str, str],
    cache_dir: Path,
) -> "Path | None":
    """Return the first usable base INI file from *hierarchy*.

    For each source in order:
    - If the stored path is an HTTP(S) URL, check the channel's cache dir for
      ``base.ini`` (the only URL-backed source currently supported is ``global``).
    - Otherwise treat the stored path as a local file path and return it if it
      exists.

    Returns ``None`` when no source produces a readable file.
    """
    _URL_CACHE_MAP = {"global": "base.ini"}

    for source_name in hierarchy:
        source_path = source_paths.get(source_name, "")
        if not source_path:
            continue

        if source_path.startswith("http://") or source_path.startswith("https://"):
            cache_filename = _URL_CACHE_MAP.get(source_name)
            if cache_filename:
                candidate = cache_dir / cache_filename
                if candidate.exists():
                    return candidate
        elif Path(source_path).exists():
            return Path(source_path)

    return None
