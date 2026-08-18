"""Extracts files from Star Citizen's Data.p4k using unp4k.exe."""

import hashlib
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.utils.dataforge_contract import DATAFORGE_KEEP_SUBPATHS
from src.utils.file_utils import robust_rmtree
from src.utils.perf import timed

logger = logging.getLogger(__name__)

# Track active subprocesses by Python thread-id so they can be killed
# from the main thread when the app closes mid-extraction.
_active_procs: dict[int, subprocess.Popen] = {}
_active_procs_lock = threading.Lock()


# Path of global.ini inside the p4k archive (unp4k preserves directory structure)
_GLOBAL_INI_RELATIVE = Path("data/Localization/english/global.ini")


# dataforge_contract.py owns the retained subtrees the enhancement generator
# reads. Everything else unforge produces is copied nowhere
# — the temp extraction is thrown away when the with-block exits.
#
# Keeping this list tight:
#   * halves the final cache's file count (~58k → ~28k) and disk footprint
#     (~2.4 GB → ~1.4 GB);
#   * cuts the temp → cache copy step to ~50% of its old wall-clock (OneDrive
#     / Defender / Indexer fire hooks per-file-close, which dominates copy
#     time on typical Windows installs);
#   * makes ``_robust_rmtree`` on the old cache roughly 2x faster and less
#     prone to transient WinError 5 retries, since there are half as many
#     files for the AV/indexer stack to hold open briefly.
#
# unp4k and unforge themselves are unaffected — unforge has no filter flag,
# so we still produce the full DCB-expansion into the temp dir. The savings
# are on the persistent cache, not on the first-time CPU work.
#
# MAINTENANCE CONTRACT: paths here must cover everything ``scripts/
# generate_enhancements_ini.py`` reads via ``records / ...``. If a future
# generator feature reads a new subtree, add it here or the cache won't
# contain it and enhancements for that subtree will silently be empty.
# ``tests/test_pak_extraction.py`` derives generator reads from its AST and
# verifies they remain covered by this contract.
DATAFORGE_IDENTITY_FILE = ".dataforge_identity.json"
DATAFORGE_CACHE_SCHEMA_VERSION = 2
DATAFORGE_PRISTINE_DIR = "pristine"
DATAFORGE_PATCHED_DIR = "raw"
DATAFORGE_REQUIRED_HEALTH_SUBPATHS = ("entities/scitem", "entities/spaceships")


@dataclass(frozen=True)
class DataForgeHealthReport:
    """Essential DataForge cache health evidence collected before activation."""

    xml_counts: dict[str, int]

    def summary_line(self) -> str:
        return ", ".join(f"{path}: {count} XML" for path, count in self.xml_counts.items())


def _copy_filtered_records(src_libs: Path, dst_libs: Path) -> tuple[int, int]:
    """Copy only the generator's required subtrees from *src_libs* → *dst_libs*.

    Both paths point at the ``libs/`` directory unforge writes (which in turn
    contains ``foundry/records/<subtree>/...``). Only subpaths listed in
    :data:`DATAFORGE_KEEP_SUBPATHS` are copied; anything else in the source
    is left in the temp dir and dropped when the surrounding TemporaryDirectory
    context exits.

    Returns ``(copied, skipped)`` — the number of keep-subpaths actually
    present and copied, and the number that weren't in this game build
    (common for ``entities/missions`` etc. which appear and disappear between
    patches — the generator already guards each read with ``if dir.exists()``).
    """
    records_src = src_libs / "foundry" / "records"
    records_dst = dst_libs / "foundry" / "records"

    if not records_src.exists():
        raise FileNotFoundError(f"unforge output missing expected 'foundry/records/' layout at {records_src}")

    records_dst.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for rel in DATAFORGE_KEEP_SUBPATHS:
        src = records_src / rel
        dst = records_dst / rel
        if not src.exists():
            # Not every build ships every subtree — e.g. entities/missions,
            # entities/contracts, entities/jobterminal came and went across
            # 4.x patches. Log at debug so the cold-path message in the Log
            # Tab stays uncluttered.
            logger.debug(f"DataForge keep-path not in this build, skipping: {rel}")
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        copied += 1

    return copied, skipped


def validate_dataforge_cache(cache_dir: Path) -> DataForgeHealthReport:
    """Require parseable XML in the essential patched DataForge subtrees."""
    records = cache_dir / DATAFORGE_PATCHED_DIR / "libs" / "foundry" / "records"
    counts: dict[str, int] = {}
    for subpath in DATAFORGE_REQUIRED_HEALTH_SUBPATHS:
        count = 0
        for xml_file in (records / subpath).rglob("*.xml"):
            count += 1
            try:
                ET.parse(xml_file)
            except ET.ParseError as exc:
                raise RuntimeError(f"DataForge health check failed: invalid XML in {xml_file}: {exc}") from exc
        if count == 0:
            raise RuntimeError(f"DataForge health check failed: no XML files under required subtree {subpath}")
        counts[subpath] = count
    return DataForgeHealthReport(xml_counts=counts)


def _has_required_dataforge_xml(cache_dir: Path) -> bool:
    records = cache_dir / DATAFORGE_PATCHED_DIR / "libs" / "foundry" / "records"
    return all(
        next((records / subpath).rglob("*.xml"), None) is not None for subpath in DATAFORGE_REQUIRED_HEALTH_SUBPATHS
    )


def _replace_dataforge_cache(staging_dir: Path, cache_dir: Path) -> None:
    """Replace *cache_dir* with a complete staged cache, restoring it on swap failure."""
    backup_dir = cache_dir.with_name(f".{cache_dir.name}.backup-{uuid.uuid4().hex}")
    had_cache = cache_dir.exists()
    try:
        if had_cache:
            _replace_with_retry(cache_dir, backup_dir)
        _replace_with_retry(staging_dir, cache_dir)
    except OSError:
        if had_cache and backup_dir.exists() and not cache_dir.exists():
            _replace_with_retry(backup_dir, cache_dir)
        raise
    if backup_dir.exists():
        try:
            robust_rmtree(backup_dir)
        except OSError:
            logger.warning("DataForge cache backup remains after successful replacement: %s", backup_dir)


def _replace_with_retry(source: Path, target: Path, attempts: int = 6) -> None:
    """Rename a directory with bounded retries for transient Windows locks."""
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except OSError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            delay = min(0.2 * (2**attempt), 3.0)
            logger.warning("rename %s -> %s failed (%s); retrying in %.1fs", source, target, exc, delay)
            time.sleep(delay)
    raise last_error if last_error else OSError(f"Failed to rename {source} to {target}")


def _recover_dataforge_cache(cache_dir: Path) -> None:
    """Restore the newest stranded cache backup when an interrupted swap left no live cache."""
    if cache_dir.exists():
        return
    backups = sorted(
        cache_dir.parent.glob(f".{cache_dir.name}.backup-*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        return
    backup = backups[0]
    logger.warning("Restoring DataForge cache from interrupted replacement backup: %s", backup)
    _replace_with_retry(backup, cache_dir)


def _recover_dataforge_layer(cache_dir: Path, layer: str) -> None:
    """Restore a stranded layer backup after an interrupted in-cache replacement."""
    target = cache_dir / layer
    if target.exists():
        return
    backups = sorted(
        cache_dir.glob(f".{layer}.backup-*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        return
    backup = backups[0]
    logger.warning("Restoring DataForge %s layer from interrupted replacement backup: %s", layer, backup)
    _replace_with_retry(backup, target)


def _file_identity(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def patch_set_fingerprint(patch_root: Path) -> str:
    """Return a content fingerprint for every declarative DataForge patch."""
    digest = hashlib.sha256()
    for patch_file in sorted(patch_root.rglob("*.patch.json")) if patch_root.exists() else []:
        digest.update(str(patch_file.relative_to(patch_root)).encode("utf-8"))
        digest.update(patch_file.read_bytes())
    return digest.hexdigest()


def _write_dataforge_identity(
    cache_dir: Path,
    p4k_path: Path,
    unp4k_exe: Path,
    unforge_exe: Path,
    patch_fingerprint: str,
) -> None:
    """Write the immutable inputs and patch set that produced this cache."""
    identity = {
        "schema_version": DATAFORGE_CACHE_SCHEMA_VERSION,
        "p4k": _file_identity(p4k_path),
        "tools": {"unp4k": _file_identity(unp4k_exe), "unforge": _file_identity(unforge_exe)},
        "patch_fingerprint": patch_fingerprint,
    }
    (cache_dir / DATAFORGE_IDENTITY_FILE).write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")


def _read_dataforge_identity(cache_dir: Path) -> dict | None:
    try:
        return json.loads((cache_dir / DATAFORGE_IDENTITY_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def rebuild_patched_dataforge_cache(
    cache_dir: Path,
    patch_fingerprint: str,
    finalize_callback: Callable[[Path], None],
) -> bool:
    """Rebuild the patched ``raw`` tree from immutable ``pristine`` XML when patches change."""
    _recover_dataforge_layer(cache_dir, DATAFORGE_PATCHED_DIR)
    identity = _read_dataforge_identity(cache_dir)
    if identity is None or identity.get("patch_fingerprint") == patch_fingerprint:
        return False

    pristine_libs = cache_dir / DATAFORGE_PRISTINE_DIR / "libs"
    if not pristine_libs.exists():
        raise FileNotFoundError(f"Pristine DataForge cache missing at {pristine_libs}")

    staging_root = cache_dir / f".{DATAFORGE_PATCHED_DIR}.staging-{uuid.uuid4().hex}"
    try:
        shutil.copytree(pristine_libs, staging_root / DATAFORGE_PATCHED_DIR / "libs")
        finalize_callback(staging_root)
        health = validate_dataforge_cache(staging_root)
        logger.info("DataForge patched-cache health check passed: %s", health.summary_line())
        _replace_dataforge_cache(staging_root / DATAFORGE_PATCHED_DIR, cache_dir / DATAFORGE_PATCHED_DIR)
        identity["patch_fingerprint"] = patch_fingerprint
        (cache_dir / DATAFORGE_IDENTITY_FILE).write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
        return True
    finally:
        if staging_root.exists():
            robust_rmtree(staging_root)


def _run_subprocess(
    args: list[str],
    *,
    cwd: str | None = None,
    timeout: int | float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with stdout/stderr capture and no console window.

    Uses Popen so the active process is registered in ``_active_procs`` and
    can be killed from the main thread if the app closes mid-extraction.
    """
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)) if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=flags,
    )
    tid = threading.get_ident()
    with _active_procs_lock:
        _active_procs[tid] = proc
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
    finally:
        with _active_procs_lock:
            _active_procs.pop(tid, None)
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


def kill_active_subprocess(thread_id: int) -> None:
    """Kill the subprocess currently running in *thread_id*, if any.

    Called from the main thread when the app is closing while a long-running
    extraction is in progress, so the temp directory can be cleaned up.
    """
    with _active_procs_lock:
        proc = _active_procs.get(thread_id)
    if proc is not None:
        try:
            proc.kill()
        except OSError:
            pass


@timed
def extract_global_ini(
    p4k_path: Path,
    output_path: Path,
    unp4k_exe: Path,
    progress_callback=None,
    progress_pct_callback=None,
) -> bool:
    """Extract global.ini from Data.p4k and save it to output_path.

    Uses unp4k.exe with the filter "global.ini" to extract only the localization
    file, then copies it to output_path (overwriting any existing file).

    Args:
        p4k_path: Path to Star Citizen's Data.p4k file.
        output_path: Destination path (e.g. cache/base.ini).
        unp4k_exe: Path to the locally-cached unp4k.exe.
        progress_callback: Optional callable(str) for status messages.

    Returns:
        True on success.

    Raises:
        FileNotFoundError: If unp4k.exe or Data.p4k is missing, or the
            extracted file is not found after extraction.
        RuntimeError: If unp4k.exe exits with a non-zero return code.
    """
    if not unp4k_exe.exists():
        raise FileNotFoundError(f"unp4k.exe not found at: {unp4k_exe}")
    if not p4k_path.exists():
        raise FileNotFoundError(f"Data.p4k not found at: {p4k_path}")

    TOTAL_PHASES = 2
    with tempfile.TemporaryDirectory() as tmp_dir:
        if progress_callback:
            progress_callback("Launching unp4k — this may take a minute...")
        if progress_pct_callback:
            progress_pct_callback(0, TOTAL_PHASES, "Launching unp4k…")

        logger.info(f"Running unp4k: {unp4k_exe} {p4k_path} global.ini (cwd={tmp_dir})")
        result = _run_subprocess(
            [str(unp4k_exe), str(p4k_path), "global.ini"],
            cwd=tmp_dir,
            timeout=300,
        )

        if result.returncode != 0:
            logger.error(f"unp4k stderr: {result.stderr}")
            raise RuntimeError(f"unp4k.exe exited with code {result.returncode}.\n\n{result.stderr or result.stdout}")

        extracted = Path(tmp_dir) / _GLOBAL_INI_RELATIVE
        if not extracted.exists():
            raise FileNotFoundError(
                f"unp4k ran successfully but global.ini was not found at the expected path:\n"
                f"{extracted}\n\n"
                f"stdout: {result.stdout[:500]}"
            )

        if progress_callback:
            progress_callback("Copying extracted global.ini to cache...")
        if progress_pct_callback:
            progress_pct_callback(1, TOTAL_PHASES, "Copying extracted global.ini…")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(extracted), str(output_path))
        logger.info(f"Extracted global.ini → {output_path}")

    if progress_pct_callback:
        progress_pct_callback(2, TOTAL_PHASES, "Done")
    return True


@timed
def extract_dataforge(
    p4k_path: Path,
    unp4k_exe: Path,
    unforge_exe: Path,
    dataforge_cache_dir: Path,
    progress_callback=None,
    progress_pct_callback=None,
    finalize_callback: Callable[[Path], None] | None = None,
    patch_fingerprint: str = "",
) -> bool:
    """Extract DataForge entity XMLs from Data.p4k and cache them.

    Pipeline:
      1. unp4k.exe extracts Game2.dcb from the p4k into a temp directory.
      2. unforge.exe converts Game2.dcb → individual XML entity files.
      3. The full extraction is cached to dataforge_cache_dir for stats generation.

    This is slow the first time (~several minutes) but results are cached and
    only need to be re-run when the p4k file changes.

    Args:
        p4k_path: Path to Data.p4k.
        unp4k_exe: Path to locally-cached unp4k.exe.
        unforge_exe: Path to locally-cached unforge.exe.
        dataforge_cache_dir: Destination directory for the cached entity XMLs.
        progress_callback: Optional callable(str) for status messages.

    Returns:
        True on success.

    Raises:
        FileNotFoundError: If required executables or Data.p4k are missing.
        RuntimeError: If either subprocess fails.
    """
    for exe, name in [(unp4k_exe, "unp4k.exe"), (unforge_exe, "unforge.cli.exe")]:
        if not exe.exists():
            raise FileNotFoundError(f"{name} not found at: {exe}")
    if not p4k_path.exists():
        raise FileNotFoundError(f"Data.p4k not found at: {p4k_path}")

    _recover_dataforge_cache(dataforge_cache_dir)

    TOTAL_PHASES = 3
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp = Path(tmp_dir)

        # ── Step 1: Extract Game2.dcb ─────────────────────────────────────────
        if progress_callback:
            progress_callback("Extracting Game2.dcb from Data.p4k…")
        if progress_pct_callback:
            progress_pct_callback(0, TOTAL_PHASES, "Extracting Game2.dcb from Data.p4k…")
        logger.info(f"Running unp4k to extract .dcb: {unp4k_exe} {p4k_path} .dcb")
        result = _run_subprocess(
            [str(unp4k_exe), str(p4k_path), ".dcb"],
            cwd=tmp_dir,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"unp4k.exe failed (code {result.returncode}):\n{result.stderr or result.stdout}")

        # unp4k preserves archive structure: Data/Game2.dcb
        dcb_candidates = list(tmp.glob("Data/Game*.dcb"))
        if not dcb_candidates:
            raise FileNotFoundError("Game*.dcb not found in p4k output — check game install path.")
        dcb_path = dcb_candidates[0]
        logger.info(f"Found DCB: {dcb_path} ({dcb_path.stat().st_size / 1_048_576:.0f} MB)")

        # ── Step 2: Run unforge to produce entity XMLs ────────────────────────
        if progress_callback:
            progress_callback("Converting DataForge database — this takes several minutes…")
        if progress_pct_callback:
            progress_pct_callback(1, TOTAL_PHASES, "Converting DataForge database…")
        logger.info(f"Running unforge: {unforge_exe} {dcb_path}")
        result = _run_subprocess(
            [str(unforge_exe), str(dcb_path)],
            cwd=str(tmp_dir),
            timeout=1800,  # 30 minutes max
        )
        # A zero-length stdout + sub-second runtime is typically a silent
        # failure — e.g. AV quarantining a temp file, or unforge choking
        # on a new DCB schema. Without this log the downstream
        # "libs/ directory was not created" error gives no clue what went wrong.
        _stdout = (result.stdout or "").strip()
        _stderr = (result.stderr or "").strip()
        if _stdout:
            logger.info(f"unforge stdout ({len(_stdout)} bytes, truncated): {_stdout[:2000]}")
        if _stderr:
            logger.info(f"unforge stderr ({len(_stderr)} bytes, truncated): {_stderr[:2000]}")
        if result.returncode != 0:
            raise RuntimeError(f"unforge.exe failed (code {result.returncode}):\n{_stderr or _stdout or '(no output)'}")

        # unforge writes entity XMLs into a libs/ subdirectory next to the
        # dcb file. When it's missing we surface whatever we captured from
        # unforge's stdout/stderr in the exception so the user (and the Log
        # Tab) can see what went wrong.
        libs_dir = dcb_path.parent
        if not (libs_dir / "libs").exists():
            diagnostic = ""
            if _stdout or _stderr:
                diagnostic = (
                    f"\n\nunforge stdout:\n{_stdout[:1500] or '(empty)'}"
                    f"\n\nunforge stderr:\n{_stderr[:1500] or '(empty)'}"
                )
            else:
                # Nothing on either stream and no libs/ — unforge exited
                # silently without producing output. This can happen if the
                # executable is blocked by antivirus or the .dcb file is
                # corrupt/unreadable.
                from src.utils.tools_manager import get_tools_dir

                diagnostic = (
                    "\n\nNo output from unforge and no libs/ directory produced. "
                    "unforge.exe may be blocked by antivirus software. "
                    "Try adding an exclusion for the tools cache folder:\n"
                    f"{get_tools_dir()}\n"
                    "then run the extraction again."
                )
            raise FileNotFoundError(
                "unforge ran but libs/ directory was not created — unexpected output structure." + diagnostic
            )

        # ── Step 3: Cache the full extraction ─────────────────────────────────
        if progress_callback:
            progress_callback("Caching entity files…")
        if progress_pct_callback:
            progress_pct_callback(2, TOTAL_PHASES, "Caching entity files…")

        staging_dir = dataforge_cache_dir.with_name(f".{dataforge_cache_dir.name}.staging-{uuid.uuid4().hex}")
        if staging_dir.exists():
            robust_rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Cache only the subtrees the enhancement generator actually reads.
        # See DATAFORGE_KEEP_SUBPATHS for the list and rationale — dropping
        # the unused ~30k/~1 GB worth of entries halves cache file count and
        # makes every re-extract + clear-cache noticeably faster on the
        # OneDrive/Defender/Indexer-burdened Windows paths our users live in.
        try:
            pristine_dir = staging_dir / DATAFORGE_PRISTINE_DIR
            raw_dir = staging_dir / DATAFORGE_PATCHED_DIR
            logger.info(f"Saving staged pristine DataForge extraction to {pristine_dir}…")
            copied, skipped = _copy_filtered_records(libs_dir / "libs", pristine_dir / "libs")
            logger.info(
                f"DataForge pristine cache written: {copied}/{len(DATAFORGE_KEEP_SUBPATHS)} "
                f"keep-subpaths copied ({skipped} not present in this build)"
            )
            shutil.copytree(pristine_dir / "libs", raw_dir / "libs")

            # Write a stamp so we know when this was extracted (p4k mtime).
            (staging_dir / ".p4k_mtime").write_text(str(p4k_path.stat().st_mtime))
            _write_dataforge_identity(staging_dir, p4k_path, unp4k_exe, unforge_exe, patch_fingerprint)
            if finalize_callback is not None:
                finalize_callback(staging_dir)
            health = validate_dataforge_cache(staging_dir)
            logger.info("DataForge health check passed: %s", health.summary_line())
            _replace_dataforge_cache(staging_dir, dataforge_cache_dir)
            logger.info(f"DataForge cache written to {dataforge_cache_dir}")
        finally:
            if staging_dir.exists():
                robust_rmtree(staging_dir)

    if progress_pct_callback:
        progress_pct_callback(3, TOTAL_PHASES, "Done")
    return True


@timed
def dataforge_cache_is_fresh(
    p4k_path: Path | str,
    dataforge_cache_dir: Path | str,
    unp4k_exe: Path | str | None = None,
    unforge_exe: Path | str | None = None,
    patch_root: Path | str | None = None,
) -> bool:
    """Return True if the cached DataForge XMLs are up-to-date with the p4k.

    Requires both a matching mtime stamp AND actual XML content in the cache
    so a stamp-only remnant from a failed/partial extraction returns False.
    """
    p4k_path = Path(p4k_path)
    dataforge_cache_dir = Path(dataforge_cache_dir)

    legacy_cache_dir = dataforge_cache_dir
    legacy_p4k_path = p4k_path
    legacy_order = legacy_p4k_path.suffix.lower() != ".p4k" and legacy_cache_dir.suffix.lower() == ".p4k"
    if legacy_order:
        p4k_path = legacy_cache_dir
        dataforge_cache_dir = legacy_p4k_path

    try:
        _recover_dataforge_cache(dataforge_cache_dir)
        _recover_dataforge_layer(dataforge_cache_dir, DATAFORGE_PATCHED_DIR)
    except OSError:
        logger.warning("Could not restore interrupted DataForge cache replacement", exc_info=True)
        return False

    stamp = dataforge_cache_dir / ".p4k_mtime"
    pristine_libs = dataforge_cache_dir / DATAFORGE_PRISTINE_DIR / "libs"
    libs_dir = dataforge_cache_dir / DATAFORGE_PATCHED_DIR / "libs"
    if (
        not stamp.exists()
        or not pristine_libs.exists()
        or not libs_dir.exists()
        or not _has_required_dataforge_xml(dataforge_cache_dir)
    ):
        return False
    # Verify there is at least one XML file — guards against empty extractions
    if not any(libs_dir.rglob("*.xml")):
        return False
    try:
        identity = _read_dataforge_identity(dataforge_cache_dir)
        if identity is None or identity.get("schema_version") != DATAFORGE_CACHE_SCHEMA_VERSION:
            return False
        if identity.get("p4k") != _file_identity(p4k_path):
            return False
        if unp4k_exe is not None and identity.get("tools", {}).get("unp4k") != _file_identity(Path(unp4k_exe)):
            return False
        if unforge_exe is not None and identity.get("tools", {}).get("unforge") != _file_identity(Path(unforge_exe)):
            return False
        if patch_root is not None and identity.get("patch_fingerprint") != patch_set_fingerprint(Path(patch_root)):
            return False
        cached_mtime = float(stamp.read_text().strip())
        return cached_mtime >= p4k_path.stat().st_mtime
    except Exception:
        logger.debug("dataforge_cache_is_fresh: stamp read/mtime check failed", exc_info=True)
        return False
