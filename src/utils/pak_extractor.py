"""Extracts files from Star Citizen's Data.p4k using unp4k.exe."""

import codecs
import hashlib
import io
import json
import logging
import os
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src.utils.app_constants import (
    DATAFORGE_EXPORT_IDLE_TIMEOUT_SECONDS,
    DATAFORGE_EXPORT_TOTAL_TIMEOUT_SECONDS,
    SUBPROCESS_CAPTURE_TAIL_CHARS,
    SUBPROCESS_CLEANUP_TIMEOUT_SECONDS,
    SUBPROCESS_DIAGNOSTIC_TAIL_CHARS,
    SUBPROCESS_OUTPUT_CHUNK_BYTES,
    SUBPROCESS_OUTPUT_QUEUE_SIZE,
    SUBPROCESS_PROGRESS_LINE_CHARS,
    SUBPROCESS_READER_POLL_SECONDS,
)
from src.utils.dataforge_contract import DATAFORGE_KEEP_FILE_GLOBS, DATAFORGE_KEEP_SUBPATHS
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
DATAFORGE_CACHE_SCHEMA_VERSION = 3
DATAFORGE_PRISTINE_DIR = "pristine"
DATAFORGE_PATCHED_DIR = "raw"
DATAFORGE_REQUIRED_HEALTH_SUBPATHS = ("entities/scitem", "entities/spaceships")
_EXPORT_ERROR_DETAIL_LIMIT = 5
_HEALTH_PROGRESS_INTERVAL = 256
DATAFORGE_EXPORT_MANIFEST = ".unforge-export.json"
_DCB_HEADER_SIZE = 0x78
_DCB_TABLE_ROW_SIZES = (16, 12, 8, 8)
_EXPORT_ALLOWED_GUARDS = frozenset({"struct_cycle", "record_cycle", "empty_structure"})
_EXPORT_PROGRESS_INTERVAL = 5000

# Staging/backup directory suffixes only need to be unique for the lifetime
# of a single extraction on one machine, not globally unique. A short suffix
# keeps these transient sibling directories from pushing deeply nested
# DataForge XML paths past Windows' 260-char MAX_PATH — a full 32-hex-char
# uuid4().hex added ~34 characters versus this 8-char suffix.
_TRANSIENT_SUFFIX_LEN = 8


def _transient_suffix() -> str:
    """Return a short, locally-unique suffix for staging/backup directory names."""
    return uuid.uuid4().hex[:_TRANSIENT_SUFFIX_LEN]


@dataclass(frozen=True)
class DataForgeHealthReport:
    """Essential DataForge cache health evidence collected before activation."""

    xml_counts: dict[str, int]
    export_error_files: tuple[str, ...] = ()

    def summary_line(self) -> str:
        summary = ", ".join(f"{path}: {count} usable XML" for path, count in self.xml_counts.items())
        if self.export_error_files:
            summary += f"; {len(self.export_error_files)} files contain export errors"
        return summary


def _copy_filtered_records(src_libs: Path, dst_libs: Path) -> tuple[int, int]:
    """Copy only the generator's required subtrees from *src_libs* → *dst_libs*.

    Both paths point at the ``libs/`` directory unforge writes (which in turn
    contains ``foundry/records/<subtree>/...``). Only subpaths listed in
    :data:`DATAFORGE_KEEP_SUBPATHS` are copied; anything else in the source
    is left in the temp dir and dropped when the surrounding TemporaryDirectory
    context exits.

    Returns ``(copied, skipped)`` — the number of subpaths or file patterns actually
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

    manifest_path = src_libs.parent / DATAFORGE_EXPORT_MANIFEST
    manifest_records = (
        json.loads(manifest_path.read_text(encoding="utf-8"))["records"] if manifest_path.exists() else []
    )
    for pattern in DATAFORGE_KEEP_FILE_GLOBS:
        files = sorted(records_src.glob(pattern))
        for record in manifest_records:
            original = record["originalPath"].replace("\\", "/")
            if original.startswith("libs/foundry/records/") and PurePosixPath(
                original.removeprefix("libs/foundry/records/")
            ).match(pattern):
                source = src_libs.parent / record["actualOutputPath"]
                if source not in files:
                    files.append(source)
        if not files:
            skipped += 1
            continue
        for src in files:
            dst = records_dst / src.relative_to(records_src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        copied += 1

    return copied, skipped


def _validate_dataforge_export(dcb_path: Path, progress_callback=None) -> Path:
    from src.utils.tools_manager import TOOLS_VERSION

    manifest_path = dcb_path.parent / DATAFORGE_EXPORT_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with dcb_path.open("rb") as stream:
            header = stream.read(_DCB_HEADER_SIZE)
            if len(header) != _DCB_HEADER_SIZE:
                raise ValueError("Truncated DCB header")
            version = struct.unpack_from("<i", header, 4)[0]
            if version not in (6, 7, 8):
                raise ValueError(f"Unsupported DCB version {version}")
            counts = struct.unpack_from("<5i", header, 16)
            if any(count < 0 for count in counts) or counts[-1] == 0:
                raise ValueError("Invalid DCB table counts")
            record_size = 36 if version >= 8 else 32
            record_offset = _DCB_HEADER_SIZE + sum(
                count * size for count, size in zip(counts[:4], _DCB_TABLE_ROW_SIZES, strict=True)
            )
            if record_offset + counts[-1] * record_size > dcb_path.stat().st_size:
                raise ValueError("Truncated DCB record table")
            stream.seek(record_offset)
            binary_records = {}
            for _ in range(counts[-1]):
                row = stream.read(record_size)
                struct_offset = 12 if version >= 8 else 8
                raw_guid = row[struct_offset + 4 : struct_offset + 20]
                guid = str(
                    uuid.UUID(bytes=raw_guid[4:8][::-1] + raw_guid[2:4][::-1] + raw_guid[:2][::-1] + raw_guid[8:][::-1])
                )
                if guid in binary_records:
                    raise ValueError("Duplicate binary UUID")
                binary_records[guid] = (
                    struct.unpack_from("<I", row, struct_offset)[0],
                    *struct.unpack_from("<HH", row, record_size - 4),
                )
            stream.seek(0)
            source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != 1
            or manifest.get("toolVersion") != TOOLS_VERSION
            or manifest.get("complete") is not True
        ):
            raise ValueError("Missing completed pinned-exporter manifest")
        if manifest.get("sourceSize") != dcb_path.stat().st_size or manifest.get("sourceSha256") != source_hash:
            raise ValueError("Manifest source identity mismatch")
        if manifest.get("expectedRecords") != counts[-1] or manifest.get("exportedRecords") != counts[-1]:
            raise ValueError("Manifest record count mismatch")
        if manifest.get("errors") != 0 or manifest.get("truncations") != 0:
            raise ValueError("Exporter errors or truncation reported")
        records = manifest["records"]
        if not isinstance(records, list) or len(records) != counts[-1]:
            raise ValueError("Incomplete manifest record list")
        seen_ids = set()
        seen_paths = set()
        empty_count = 0
        aggregate_guards = {}
        output_root = dcb_path.parent.resolve()
        for record in records:
            guid = record["guid"]
            metadata = (record["structIndex"], record["variant"], record["recordSize"])
            if guid in seen_ids or binary_records.get(guid) != metadata:
                raise ValueError("Duplicate or mismatched record UUID/metadata")
            seen_ids.add(guid)
            relative = record["actualOutputPath"]
            parts = relative.replace("\\", "/").split("/")
            path = output_root.joinpath(*parts).resolve()
            if any(part in ("", ".", "..") or ":" in part for part in parts) or output_root not in path.parents:
                raise ValueError("Unsafe manifest output path")
            normalized = relative.replace("\\", "/").casefold()
            if normalized in seen_paths or not relative.endswith(".xml"):
                raise ValueError("Duplicate or invalid manifest output path")
            seen_paths.add(normalized)
            guards = record["guards"]
            if not isinstance(guards, dict) or any(
                key not in _EXPORT_ALLOWED_GUARDS or type(value) is not int or value <= 0
                for key, value in guards.items()
            ):
                raise ValueError("Exporter truncation or invalid guard")
            for key, value in guards.items():
                aggregate_guards[key] = aggregate_guards.get(key, 0) + value
            root = ET.parse(path).getroot()
            if root.get("__ref") != guid or root.get("__path") != record["originalPath"] or not root.get("__type"):
                raise ValueError("Serialized root metadata mismatch")
            if root.get("__recordName", root.tag) != record["originalName"]:
                raise ValueError("Serialized root name mismatch")
            if record["status"] == "empty":
                empty_count += 1
                if (
                    set(guards) != {"empty_structure"}
                    or len(root)
                    or (root.text or "").strip()
                    or any(not key.startswith("__") for key in root.attrib)
                ):
                    raise ValueError("Metadata-only record lacks empty-body proof")
            elif record["status"] != "exported":
                raise ValueError("Record was not exported")
            for element in root.iter():
                values = (*element.attrib.values(), (element.text or "").strip(), (element.tail or "").strip())
                if element.tag.rsplit("}", 1)[-1] == "Error" or any(
                    value == "TBC" or value.startswith(("Error reading ", "Unhandled Type ")) for value in values
                ):
                    raise ValueError("Serialized exporter error")
            if progress_callback and len(seen_ids) % _EXPORT_PROGRESS_INTERVAL == 0:
                progress_callback(f"Validating exported records: {len(seen_ids):,} / {counts[-1]:,}")
        if (
            seen_ids != binary_records.keys()
            or empty_count != manifest.get("emptyRecords")
            or aggregate_guards != manifest.get("guards")
        ):
            raise ValueError("Manifest completeness/statistics mismatch")
        actual_paths = {
            path.relative_to(output_root).as_posix().casefold() for path in (output_root / "libs").rglob("*.xml")
        }
        if actual_paths != seen_paths:
            raise ValueError("Serialized XML set differs from manifest")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError, struct.error) as exc:
        raise RuntimeError(f"DataForge export integrity check failed: {exc}") from exc
    logger.info(
        "DataForge export integrity passed: %d UUID roots; %d empty; guards %s",
        len(seen_ids),
        empty_count,
        aggregate_guards,
    )
    return manifest_path


def validate_dataforge_cache(
    cache_dir: Path, progress_callback: Callable[[str], None] | None = None
) -> DataForgeHealthReport:
    """Require usable essential XML and report incomplete exporter output."""
    records = cache_dir / DATAFORGE_PATCHED_DIR / "libs" / "foundry" / "records"
    counts = dict.fromkeys(DATAFORGE_REQUIRED_HEALTH_SUBPATHS, 0)
    export_errors: list[str] = []
    if progress_callback:
        progress_callback("Checking cached DataForge records…")
    files = sorted(records.rglob("*.xml"))
    if progress_callback:
        progress_callback(f"Checking cached records: 0 / {len(files):,}")
    for index, xml_file in enumerate(files, start=1):
        if progress_callback and index % _HEALTH_PROGRESS_INTERVAL == 0:
            progress_callback(f"Checking cached records: {index:,} / {len(files):,}")
        relative_path = xml_file.relative_to(records).as_posix()
        try:
            root = ET.parse(xml_file).getroot()
        except ET.ParseError as exc:
            raise RuntimeError(f"DataForge health check failed: invalid XML in {xml_file}: {exc}") from exc
        if any(elem.tag.rsplit("}", 1)[-1] == "Error" for elem in root.iter()):
            export_errors.append(relative_path)
            if len(export_errors) <= _EXPORT_ERROR_DETAIL_LIMIT:
                logger.warning("DataForge incomplete XML export: %s", relative_path)
            continue
        for subpath in counts:
            if relative_path.startswith(subpath + "/"):
                counts[subpath] += 1
    if export_errors:
        logger.warning(
            "DataForge export errors in %d files; showing at most %d paths, full paths retained in health report",
            len(export_errors),
            _EXPORT_ERROR_DETAIL_LIMIT,
        )
    for subpath, count in counts.items():
        if count == 0:
            raise RuntimeError(f"DataForge health check failed: no usable XML files under required subtree {subpath}")
    if progress_callback:
        progress_callback(f"Checking cached records: {len(files):,} / {len(files):,}")
    return DataForgeHealthReport(xml_counts=counts, export_error_files=tuple(export_errors))


def _has_required_dataforge_xml(cache_dir: Path) -> bool:
    records = cache_dir / DATAFORGE_PATCHED_DIR / "libs" / "foundry" / "records"
    return all(
        next((records / subpath).rglob("*.xml"), None) is not None for subpath in DATAFORGE_REQUIRED_HEALTH_SUBPATHS
    )


def _replace_dataforge_cache(staging_dir: Path, cache_dir: Path) -> None:
    """Replace *cache_dir* with a complete staged cache, restoring it on swap failure."""
    backup_dir = cache_dir.with_name(f".{cache_dir.name}.backup-{_transient_suffix()}")
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
    progress_callback: Callable[[str], None] | None = None,
) -> bool:
    """Rebuild the patched ``raw`` tree from immutable ``pristine`` XML when patches change."""
    _recover_dataforge_layer(cache_dir, DATAFORGE_PATCHED_DIR)
    identity = _read_dataforge_identity(cache_dir)
    if identity is None or identity.get("patch_fingerprint") == patch_fingerprint:
        return False

    pristine_libs = cache_dir / DATAFORGE_PRISTINE_DIR / "libs"
    if not pristine_libs.exists():
        raise FileNotFoundError(f"Pristine DataForge cache missing at {pristine_libs}")

    staging_root = cache_dir / f".{DATAFORGE_PATCHED_DIR}.staging-{_transient_suffix()}"
    try:
        shutil.copytree(pristine_libs, staging_root / DATAFORGE_PATCHED_DIR / "libs")
        finalize_callback(staging_root)
        health = validate_dataforge_cache(staging_root, progress_callback)
        logger.info("DataForge patched-cache health check passed: %s", health.summary_line())
        _replace_dataforge_cache(staging_root / DATAFORGE_PATCHED_DIR, cache_dir / DATAFORGE_PATCHED_DIR)
        identity["patch_fingerprint"] = patch_fingerprint
        (cache_dir / DATAFORGE_IDENTITY_FILE).write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
        return True
    finally:
        if staging_root.exists():
            robust_rmtree(staging_root)


class _SubprocessOutputTimeout(subprocess.TimeoutExpired):
    def __init__(self, args, timeout, reason, output=None, stderr=None):
        super().__init__(args, timeout, output=output, stderr=stderr)
        self.reason = reason

    def __str__(self):
        stdout = self.output.decode(errors="replace") if isinstance(self.output, bytes) else self.output or ""
        stderr = self.stderr.decode(errors="replace") if isinstance(self.stderr, bytes) else self.stderr or ""
        stdout = stdout.strip()[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:]
        stderr = stderr.strip()[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:]
        return (
            f"Subprocess {self.reason} ({self.timeout} seconds); last output:"
            f"\nstdout:\n{stdout or '(empty)'}\nstderr:\n{stderr or '(empty)'}"
        )


def _run_subprocess(
    args: list[str],
    *,
    cwd: str | None = None,
    timeout: int | float | None = None,
    progress_callback: Callable[[str], None] | None = None,
    idle_timeout: int | float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with stdout/stderr capture and no console window.

    Uses Popen so the active process is registered in ``_active_procs`` and
    can be killed from the main thread if the app closes mid-extraction.
    Streaming callbacks run only on this caller's thread. Nonblocking pipe
    readers can stop even if a descendant retains an inherited pipe handle.
    Streaming captures retain only a bounded diagnostic tail per stream.
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
        if progress_callback is not None or idle_timeout is not None:
            events: queue.Queue = queue.Queue(maxsize=SUBPROCESS_OUTPUT_QUEUE_SIZE)
            stopping = threading.Event()
            readers: list[threading.Thread] = []
            captured = {"stdout": "", "stderr": ""}
            pending = {"stdout": "", "stderr": ""}
            started = last_output = time.monotonic()

            def enqueue(event):
                while True:
                    try:
                        events.put(event, timeout=SUBPROCESS_READER_POLL_SECONDS)
                        return True
                    except queue.Full:
                        if stopping.is_set():
                            return False

            def read_stream(name, stream):
                try:
                    os.set_blocking(stream.fileno(), False)
                    decoder = io.IncrementalNewlineDecoder(codecs.getincrementaldecoder(stream.encoding)(), True)
                    while True:
                        try:
                            chunk = os.read(stream.fileno(), SUBPROCESS_OUTPUT_CHUNK_BYTES)
                        except BlockingIOError:
                            if stopping.is_set():
                                break
                            stopping.wait(SUBPROCESS_READER_POLL_SECONDS)
                            continue
                        if not chunk:
                            tail = decoder.decode(b"", final=True)
                            if tail:
                                enqueue((name, tail, time.monotonic()))
                            break
                        if not enqueue((name, decoder.decode(chunk), time.monotonic())):
                            break
                except Exception as exc:
                    enqueue((name, exc, time.monotonic()))
                finally:
                    stream.close()
                    enqueue((name, None, time.monotonic()))

            def consume(event, notify=True):
                nonlocal last_output
                name, text, observed = event
                if isinstance(text, Exception):
                    if notify:
                        raise text
                    return
                if text is None:
                    finished.add(name)
                    text = ""
                else:
                    captured[name] = (captured[name] + text)[-SUBPROCESS_CAPTURE_TAIL_CHARS:]
                    last_output = max(last_output, observed)
                if not notify or progress_callback is None:
                    pending[name] = ""
                    return
                pending[name] += text
                while pending[name]:
                    newline = pending[name].find("\n", 0, SUBPROCESS_PROGRESS_LINE_CHARS)
                    if newline >= 0:
                        line = pending[name][:newline]
                        pending[name] = pending[name][newline + 1 :]
                    elif len(pending[name]) >= SUBPROCESS_PROGRESS_LINE_CHARS:
                        line = pending[name][:SUBPROCESS_PROGRESS_LINE_CHARS]
                        pending[name] = pending[name][SUBPROCESS_PROGRESS_LINE_CHARS:]
                    elif name in finished:
                        line, pending[name] = pending[name], ""
                    else:
                        break
                    if line.strip():
                        progress_callback(f"{name}: {line}")

            finished: set[str] = set()
            try:
                for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                    reader = threading.Thread(
                        target=read_stream, args=(name, stream), name=f"export-{name}", daemon=True
                    )
                    readers.append(reader)
                    reader.start()
                while len(finished) < 2 or proc.poll() is None:
                    now = time.monotonic()
                    reason = ""
                    limit = timeout
                    if timeout is not None and now - started >= timeout:
                        reason = "total time limit"
                    elif idle_timeout is not None and now - last_output >= idle_timeout:
                        try:
                            consume(events.get_nowait())
                        except queue.Empty:
                            reason, limit = "no output", idle_timeout
                        else:
                            continue
                    if reason:
                        raise _SubprocessOutputTimeout(args, limit, reason)
                    remaining = [SUBPROCESS_READER_POLL_SECONDS]
                    if timeout is not None:
                        remaining.append(timeout - (now - started))
                    if idle_timeout is not None:
                        remaining.append(idle_timeout - (now - last_output))
                    try:
                        consume(events.get(timeout=max(0, min(remaining))))
                    except queue.Empty:
                        pass
            except BaseException as exc:
                stopping.set()
                try:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait(timeout=SUBPROCESS_CLEANUP_TIMEOUT_SECONDS)
                except (OSError, subprocess.TimeoutExpired):
                    logger.warning("Subprocess termination did not complete cleanly", exc_info=True)
                for reader in readers:
                    reader.join(SUBPROCESS_CLEANUP_TIMEOUT_SECONDS)
                while not events.empty():
                    consume(events.get_nowait(), notify=False)
                if isinstance(exc, _SubprocessOutputTimeout):
                    raise _SubprocessOutputTimeout(
                        args,
                        exc.timeout,
                        exc.reason,
                        output=captured["stdout"],
                        stderr=captured["stderr"],
                    ) from exc
                raise
            finally:
                stopping.set()
                for reader in readers:
                    reader.join(SUBPROCESS_CLEANUP_TIMEOUT_SECONDS)
            return subprocess.CompletedProcess(args, proc.returncode, captured["stdout"], captured["stderr"])
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            stdout, stderr = proc.communicate()
            exc.output = stdout
            exc.stderr = stderr
            raise
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
        if len(dcb_candidates) != 1:
            raise RuntimeError("Multiple Game*.dcb files found; refusing ambiguous extraction")
        dcb_path = dcb_candidates[0]
        logger.info(f"Found DCB: {dcb_path} ({dcb_path.stat().st_size / 1_048_576:.0f} MB)")

        # ── Step 2: Run unforge to produce entity XMLs ────────────────────────
        if progress_callback:
            progress_callback("Exporting DataForge records — allow tens of minutes for a first extraction…")
        if progress_pct_callback:
            progress_pct_callback(1, TOTAL_PHASES, "Converting DataForge database…")
        logger.info(f"Running unforge: {unforge_exe} {dcb_path}")

        def export_progress(message):
            stream, separator, detail = message.partition(": ")
            if stream == "stdout" and separator:
                friendly = f"DataForge Exporter Progress: {detail}"
                if detail.startswith("Completed "):
                    friendly = "DataForge Exporter Progress: Export complete"
            elif stream == "stderr" and separator:
                friendly = f"DataForge Exporter Diagnostic: {detail}"
            else:
                friendly = f"DataForge Exporter Progress: {message}"
            if progress_callback:
                progress_callback(friendly)
            logger.info("%s", friendly)

        result = _run_subprocess(
            [str(unforge_exe), str(dcb_path)],
            cwd=str(tmp_dir),
            timeout=DATAFORGE_EXPORT_TOTAL_TIMEOUT_SECONDS,
            idle_timeout=DATAFORGE_EXPORT_IDLE_TIMEOUT_SECONDS,
            progress_callback=export_progress,
        )
        # A zero-length stdout + sub-second runtime is typically a silent
        # failure — e.g. AV quarantining a temp file, or unforge choking
        # on a new DCB schema. Without this log the downstream
        # "libs/ directory was not created" error gives no clue what went wrong.
        _stdout = (result.stdout or "").strip()
        _stderr = (result.stderr or "").strip()
        if _stdout:
            logger.info(f"unforge stdout ({len(_stdout)} chars, tail): {_stdout[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:]}")
        if _stderr:
            logger.info(f"unforge stderr ({len(_stderr)} chars, tail): {_stderr[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:]}")
        if result.returncode != 0:
            diagnostic = (
                f"stdout:\n{_stdout[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:] or '(empty)'}"
                f"\nstderr:\n{_stderr[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:] or '(empty)'}"
            )
            raise RuntimeError(f"unforge.exe failed (code {result.returncode}):\n{diagnostic}")

        # unforge writes entity XMLs into a libs/ subdirectory next to the
        # dcb file. When it's missing we surface whatever we captured from
        # unforge's stdout/stderr in the exception so the user (and the Log
        # Tab) can see what went wrong.
        libs_dir = dcb_path.parent
        if not (libs_dir / "libs").exists():
            diagnostic = ""
            if _stdout or _stderr:
                diagnostic = (
                    f"\n\nunforge stdout:\n{_stdout[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:] or '(empty)'}"
                    f"\n\nunforge stderr:\n{_stderr[-SUBPROCESS_DIAGNOSTIC_TAIL_CHARS:] or '(empty)'}"
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

        if progress_callback:
            progress_callback("Validating exported DataForge records…")
        export_manifest = _validate_dataforge_export(dcb_path, progress_callback)

        # ── Step 3: Cache the full extraction ─────────────────────────────────
        if progress_callback:
            progress_callback("Caching entity files…")
        if progress_pct_callback:
            progress_pct_callback(2, TOTAL_PHASES, "Caching entity files…")

        staging_dir = dataforge_cache_dir.with_name(f".{dataforge_cache_dir.name}.staging-{_transient_suffix()}")
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
                f"DataForge pristine cache written: {copied}/{len(DATAFORGE_KEEP_SUBPATHS) + len(DATAFORGE_KEEP_FILE_GLOBS)} "
                f"keep-subpaths copied ({skipped} not present in this build)"
            )
            shutil.copytree(pristine_dir / "libs", raw_dir / "libs")
            shutil.copy2(export_manifest, staging_dir / DATAFORGE_EXPORT_MANIFEST)

            # Write a stamp so we know when this was extracted (p4k mtime).
            (staging_dir / ".p4k_mtime").write_text(str(p4k_path.stat().st_mtime))
            _write_dataforge_identity(staging_dir, p4k_path, unp4k_exe, unforge_exe, patch_fingerprint)
            if finalize_callback is not None:
                finalize_callback(staging_dir)
            logger.info("Checking staged DataForge cache health")
            health = validate_dataforge_cache(staging_dir, progress_callback)
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
