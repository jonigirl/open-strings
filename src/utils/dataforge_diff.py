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
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MANIFEST_FILE = ".diff_manifest.json"
_HASH_WORKERS = max(8, (os.cpu_count() or 4) * 2)

# Maps category name → DataForge subtree prefixes it reads from.
# Paths are relative to the libs/ directory (the cache_dir argument passed to
# update_manifest and dirty_categories), so they all start with
# "foundry/records/".  Mirrors DATAFORGE_KEEP_SUBPATHS in pak_extractor.py —
# keep in sync when new subtrees are added.
CATEGORY_SUBTREES: dict[str, list[str]] = {
    "ships": ["foundry/records/entities/spaceships"],
    "components": ["foundry/records/entities/scitem"],
    "ship_weapons": [
        "foundry/records/entities/scitem/ships/weapons",
        "foundry/records/ammoparams/vehicle",
    ],
    "fps_weapons": [
        "foundry/records/entities/scitem/weapons/fps_weapons",
        "foundry/records/ammoparams/fps",
    ],
    "missions": [
        "foundry/records/missionbroker/pu_missions",
        "foundry/records/entities/missions",
        "foundry/records/entities/contracts",
        "foundry/records/entities/jobterminal",
        "foundry/records/contracts/contractgenerator",
        "foundry/records/contracts/contracttemplates",
        "foundry/records/crafting/blueprintrewards",
        "foundry/records/crafting/blueprints/crafting",
        "foundry/records/reputation/rewards/missionrewards_reputation",
    ],
    "commodities": [
        "foundry/records/crafting/blueprints/crafting",
        "foundry/records/entities/scitem",
    ],
    "journal": [
        "foundry/records/crafting/blueprints/crafting",
        "foundry/records/entities/scitem",
    ],
}


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


def _build_snapshot(
    cache_dir: Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, dict]:
    """Walk the dataforge cache and return a snapshot dict:
        { "relative/path.xml": {"mtime": float, "sha256": str}, ... }
    Uses a ThreadPoolExecutor for parallel SHA-256 hashing.
    """
    paths: list[tuple[Path, str]] = []
    for root, _, files in os.walk(cache_dir):
        for fname in files:
            if not fname.endswith(".xml"):
                continue
            abs_path = Path(root) / fname
            rel = str(abs_path.relative_to(cache_dir)).replace("\\", "/")
            paths.append((abs_path, rel))

    total = len(paths)
    if progress_callback:
        progress_callback(0, total, f"Snapshotting cache for diff (0/{total})\u2026")

    snapshot: dict[str, dict] = {}
    if total == 0:
        return snapshot

    def _hash_one(item: tuple[Path, str]) -> tuple[str, dict]:
        abs_path, rel = item
        return rel, {"mtime": abs_path.stat().st_mtime, "sha256": _hash_file(abs_path)}

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
    with open(_manifest_path(cache_dir), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, separators=(",", ":"))


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

    with open(manifest_file, encoding="utf-8") as f:
        old: dict[str, dict] = json.load(f)

    new = _build_snapshot(cache_dir)

    # Find changed paths (added, removed, or different hash)
    all_paths = set(old) | set(new)
    changed: set[str] = set()
    for rel in all_paths:
        if rel not in old or rel not in new:
            changed.add(rel)  # added or removed
        elif old[rel]["mtime"] != new[rel]["mtime"]:
            # mtime differs — confirm with hash before marking dirty
            if old[rel]["sha256"] != new[rel]["sha256"]:
                changed.add(rel)

    if not changed:
        return set()  # clean — skip all generators

    # Map changed paths → categories
    dirty: set[str] = set()
    for rel_path in changed:
        for category, subtrees in CATEGORY_SUBTREES.items():
            if any(rel_path.startswith(prefix) for prefix in subtrees):
                dirty.add(category)
                break

    return dirty
