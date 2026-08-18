"""
dataforge_diff.py — Diff-cache for the DataForge XML cache.

Usage
-----
After unforge writes the cache, call `update_manifest` to snapshot it.
Before running enhancement generators, call `dirty_categories` to find
out which ones actually need to re-run.

    from src.utils.dataforge_diff import update_manifest, dirty_categories

    # After a successful extraction:
    update_manifest(cache_dir)

    # Before each generator run:
    dirty = dirty_categories(cache_dir)
    # dirty == None  →  no prior manifest exists; run everything
    # dirty == set() →  nothing changed; skip everything
    # dirty == {"ships", "missions"} →  only re-run those two
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.utils.dataforge_contract import DATAFORGE_CATEGORY_SUBTREES
from src.utils.file_utils import atomic_write_text

logger = logging.getLogger(__name__)

MANIFEST_FILE = ".diff_manifest.json"
_HASH_WORKERS = max(8, (os.cpu_count() or 4) * 2)

# Maps category name → DataForge subtree prefixes it reads from.
# Paths are relative to the libs/ directory (the cache_dir argument passed to
# update_manifest and dirty_categories), so they all start with
# "foundry/records/". Defined with the keep-list in dataforge_contract.py.
CATEGORY_SUBTREES = DATAFORGE_CATEGORY_SUBTREES


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_file(path: Path) -> str:
    """SHA-256 of file content, hex-encoded."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _xml_file_metadata(cache_dir: Path) -> dict[str, tuple[Path, int, int]]:
    """Return XML paths with their size and nanosecond mtime without reading content."""
    metadata: dict[str, tuple[Path, int, int]] = {}
    for root, _, files in os.walk(cache_dir):
        for filename in files:
            if not filename.endswith(".xml"):
                continue
            path = Path(root) / filename
            stat = path.stat()
            rel = str(path.relative_to(cache_dir)).replace("\\", "/")
            metadata[rel] = (path, stat.st_size, stat.st_mtime_ns)
    return metadata


def _build_snapshot(
    cache_dir: Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, dict]:
    """Walk the dataforge cache and return a snapshot dict:
        { "relative/path.xml": {"mtime": float, "sha256": str}, ... }
    Uses a ThreadPoolExecutor for parallel SHA-256 hashing.
    """
    metadata = _xml_file_metadata(cache_dir)
    paths = [(path, rel, size, mtime_ns) for rel, (path, size, mtime_ns) in metadata.items()]

    total = len(paths)
    if progress_callback:
        progress_callback(0, total, f"Snapshotting cache for diff (0/{total})\u2026")

    snapshot: dict[str, dict] = {}
    if total == 0:
        return snapshot

    def _hash_one(item: tuple[Path, str, int, int]) -> tuple[str, dict]:
        abs_path, rel, size, mtime_ns = item
        return rel, {
            "mtime": abs_path.stat().st_mtime,
            "mtime_ns": mtime_ns,
            "size": size,
            "sha256": _hash_file(abs_path),
        }

    completed = 0
    next_report = 256
    with ThreadPoolExecutor(max_workers=_HASH_WORKERS) as pool:
        for fut in as_completed(pool.submit(_hash_one, item) for item in paths):
            rel, entry = fut.result()
            snapshot[rel] = entry
            completed += 1
            if progress_callback and completed >= next_report:
                progress_callback(
                    completed,
                    total,
                    f"Snapshotting cache for diff ({completed}/{total})\u2026",
                )
                next_report = completed + 256

    if progress_callback:
        progress_callback(total, total, f"Snapshotting cache for diff ({total}/{total})\u2026")

    return snapshot


def _manifest_path(cache_dir: Path) -> Path:
    return cache_dir / MANIFEST_FILE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_manifest(
    cache_dir: Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    """Snapshot the current state of the DataForge cache and persist it.

    Call this *after* a successful extraction so the next run can diff
    against it.  Pass *progress_callback(completed, total, message)* to
    surface SHA-256 progress on the UI.
    """
    cache_dir = Path(cache_dir)
    snapshot = _build_snapshot(cache_dir, progress_callback=progress_callback)
    atomic_write_text(_manifest_path(cache_dir), json.dumps(snapshot, separators=(",", ":")))


def dirty_categories(cache_dir: Path) -> set[str] | None:
    """Compare the current DataForge cache against the stored manifest and
    return the set of category names whose source XMLs have changed.

    Return values:
        None        — no prior manifest exists; treat all categories as dirty
        set()       — nothing changed; all generators can be skipped
        {"ships", …} — only these categories need to re-run
    """
    cache_dir = Path(cache_dir)
    manifest_file = _manifest_path(cache_dir)

    if not manifest_file.exists():
        return None  # first run — regenerate everything

    try:
        with open(manifest_file, encoding="utf-8") as file:
            old: dict[str, dict] = json.load(file)
    except (OSError, json.JSONDecodeError):
        logger.warning("DataForge diff manifest is unreadable; forcing full regeneration", exc_info=True)
        return None

    new = _build_snapshot(cache_dir)

    # Compare every content hash. Metadata is preserved in the manifest for
    # diagnostics, but cannot be trusted as an integrity signal because a
    # same-size edit can restore its original timestamp.
    all_paths = set(old) | set(new)
    changed: set[str] = set()
    for rel in all_paths:
        if rel not in old or rel not in new:
            changed.add(rel)  # added or removed
        elif old[rel].get("sha256") != new[rel].get("sha256"):
            changed.add(rel)

    if not changed:
        return set()  # clean — skip all generators

    # Map changed paths → categories
    dirty: set[str] = set()
    for rel_path in changed:
        for category, subtrees in CATEGORY_SUBTREES.items():
            if any(rel_path.startswith(prefix) for prefix in subtrees):
                dirty.add(category)

    return dirty
