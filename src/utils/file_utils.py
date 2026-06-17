"""General filesystem utilities for Open Strings."""

import gc
import logging
import os
import shutil
import stat
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def robust_rmtree(path: Path, attempts: int = 6) -> None:
    """Delete *path* recursively, surviving transient Windows locks.

    On Windows — especially when the target lives under OneDrive — rmtree
    often trips over three things:

    1. Read-only attribute on files unp4k/unforge just wrote. Clearing the
       bit via ``os.chmod(.., stat.S_IWRITE)`` lets the retry succeed.
    2. A ghost handle from the just-exited ``unforge.exe`` child process
       (or Windows Defender / Search Indexer / OneDrive client) that
       releases a beat later. A short sleep-and-retry loop clears these.
    3. A non-empty directory whose children are mid-delete. Re-walking the
       tree on each attempt catches files added or unlocked between tries.

    Silently succeeds if *path* doesn't exist. Raises the last error if
    every attempt fails so callers can surface it to the user.
    """
    if not path.exists():
        return

    def _onexc(func, target, *_):
        # Compat shim: accepts both Python 3.12 (onexc) and ≤3.11 (onerror)
        # callback signatures. Clear the read-only bit and retry.
        try:
            os.chmod(target, stat.S_IWRITE)
        except OSError:
            pass
        try:
            func(target)
        except OSError:
            raise

    last_err: Exception | None = None
    for i in range(attempts):
        try:
            gc.collect()  # drop any lingering XML file handles we own
            shutil.rmtree(path, onexc=_onexc)
            return
        except OSError as e:
            last_err = e
            # Exponential-ish backoff: 0.2, 0.4, 0.8, 1.5, 3.0 seconds. Total
            # ceiling ~6s before we bail, enough to outlast most AV/indexer
            # scans without hanging the UI forever.
            delay = min(0.2 * (2**i), 3.0)
            logger.warning(f"rmtree {path} attempt {i + 1}/{attempts} failed ({e}); retrying in {delay:.1f}s")
            time.sleep(delay)

    raise last_err if last_err else OSError(f"Failed to remove {path}")
