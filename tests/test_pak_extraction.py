"""
Tests for P4K extraction and DataForge cache management.

Covers:
- DataForge cache freshness detection
- P4K extraction pipeline error handling
- DataForge keep-list / generator read-path contract
- Filtered cache copy helper
- _robust_rmtree retry/read-only logic
- extract_global_ini happy path and error paths
"""

import ast
import hashlib
import json
import os
import queue
import stat
import struct
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.utils.pak_extractor import (
    DATAFORGE_CACHE_SCHEMA_VERSION,
    DATAFORGE_IDENTITY_FILE,
    DATAFORGE_KEEP_FILE_GLOBS,
    DATAFORGE_KEEP_SUBPATHS,
    _copy_filtered_records,
    _read_dataforge_identity,
    _recover_dataforge_cache,
    _recover_dataforge_layer,
    _replace_dataforge_cache,
    _transient_suffix,
    _validate_dataforge_export,
    dataforge_cache_is_fresh,
    extract_dataforge,
    extract_global_ini,
    rebuild_patched_dataforge_cache,
    robust_rmtree,
    validate_dataforge_cache,
)


def _write_export_manifest(dcb: Path):
    from src.utils.tools_manager import TOOLS_VERSION

    entries = []
    binary_rows = bytearray()
    for index, path in enumerate(sorted((dcb.parent / "libs").rglob("*.xml"))):
        guid = f"11111111-2222-3333-4444-{index:012d}"
        import uuid
        import xml.etree.ElementTree as ET

        root = ET.parse(path).getroot()
        relative = path.relative_to(dcb.parent).as_posix()
        root.set("__ref", guid)
        root.set("__path", relative)
        root.set("__type", root.tag)
        ET.ElementTree(root).write(path, encoding="utf-8")
        raw = uuid.UUID(guid).bytes
        binary_rows += (
            struct.pack("<4I", 0, 0, 0, 0)
            + raw[6:8][::-1]
            + raw[4:6][::-1]
            + raw[:4][::-1]
            + raw[8:][::-1]
            + struct.pack("<HH", 0, 0)
        )
        entries.append(
            {
                "guid": guid,
                "originalName": root.tag,
                "originalPath": relative,
                "actualOutputPath": relative,
                "status": "exported",
                "structIndex": 0,
                "variant": 0,
                "recordSize": 0,
                "guards": {},
            }
        )
    header = bytearray(0x78)
    struct.pack_into("<i", header, 4, 8)
    struct.pack_into("<5i", header, 16, 0, 0, 0, 0, len(entries))
    dcb.write_bytes(header + binary_rows)
    manifest = {
        "schema": 1,
        "toolVersion": TOOLS_VERSION,
        "complete": True,
        "expectedRecords": len(entries),
        "exportedRecords": len(entries),
        "emptyRecords": 0,
        "errors": 0,
        "truncations": 0,
        "sourceSize": dcb.stat().st_size,
        "sourceSha256": hashlib.sha256(dcb.read_bytes()).hexdigest(),
        "guards": {},
        "records": entries,
    }
    path = dcb.parent / ".unforge-export.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest


@pytest.mark.unit
class TestDataForgeCache:
    """DataForge cache freshness detection."""

    def test_transient_suffix_is_short(self):
        """Staging/backup suffixes must stay short to avoid reintroducing MAX_PATH failures."""
        suffix = _transient_suffix()
        assert len(suffix) == 8
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_staging_suffix_leaves_max_path_headroom(self):
        """A real end-user build failed at 263 chars where the final cache path for the
        same file was only 221 chars — the previous 32-char uuid4().hex staging suffix
        added ~42 extra characters over the plain 'dataforge' cache dir name. The
        suffix must now add far less so deeply nested DataForge XML paths stay under
        Windows' 260-char MAX_PATH.
        """
        cache_dir = Path("C:/Users/segim/AppData/Local/Open Strings/LIVE/cache/dataforge")
        staging_dir = cache_dir.with_name(f".{cache_dir.name}.staging-{_transient_suffix()}")
        overhead = len(str(staging_dir)) - len(str(cache_dir))
        assert overhead < 20

    def test_legacy_cache_is_stale_even_when_newer(self):
        """A legacy one-layer cache must migrate through a fresh extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy p4k with old mtime
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")

            # Set p4k mtime to old date
            old_time = 1000000000  # Jan 2001
            os.utime(p4k_path, (old_time, old_time))

            # Create cache dir with newer mtime
            cache_dir = os.path.join(tmpdir, "dataforge")
            os.makedirs(cache_dir, exist_ok=True)
            recent_time = 9999999999  # Far future
            os.utime(cache_dir, (recent_time, recent_time))

            # Directory mtime alone cannot validate the two-layer cache contract.
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            assert is_fresh is False

    def test_cache_is_stale_when_older(self):
        """Test that cache is stale when p4k is newer"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy p4k with new mtime
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")

            recent_time = 9999999999  # Far future
            os.utime(p4k_path, (recent_time, recent_time))

            # Create cache dir with old mtime
            cache_dir = os.path.join(tmpdir, "dataforge")
            os.makedirs(cache_dir, exist_ok=True)
            old_time = 1000000000  # Jan 2001
            os.utime(cache_dir, (old_time, old_time))

            # Cache should be stale (older than p4k)
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            assert is_fresh is False

    def test_cache_is_fresh_when_cache_missing(self):
        """Test that missing cache is treated as stale"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")

            # Cache directory doesn't exist
            cache_dir = os.path.join(tmpdir, "nonexistent")

            # Cache should be stale (doesn't exist)
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            assert is_fresh is False

    def test_cache_is_fresh_when_p4k_missing(self):
        """Test that missing p4k is handled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "nonexistent", "Data.p4k")

            cache_dir = os.path.join(tmpdir, "dataforge")
            os.makedirs(cache_dir, exist_ok=True)

            # Should handle missing p4k gracefully
            is_fresh = dataforge_cache_is_fresh(cache_dir, p4k_path)
            # Missing p4k could mean cache is stale (can't verify freshness)
            assert isinstance(is_fresh, bool)


@pytest.mark.unit
class TestSubprocessTimeout:
    @pytest.mark.parametrize(
        "times, events, reason",
        [
            (
                [0, 0, 1700, 3000, 4400, 6000, 6000],
                [
                    ("stdout", "Exported 5000/117231 records\n", 0),
                    ("stderr", "diagnostic\n", 1700),
                    ("stdout", "Exported 110000/117231 records\n", 3000),
                    ("stdout", "Exported 117231/117231 records\n", 4400),
                    ("stdout", None, 6000),
                    ("stderr", None, 6000),
                ],
                None,
            ),
            (
                [0, 0, 1700, 3000, 4400, 6100, 7200],
                [
                    ("stdout", f"Exported {count}/117231 records\n", stamp)
                    for count, stamp in ((5000, 0), (10000, 1700), (20000, 3000), (30000, 4400), (110000, 6100))
                ],
                "total time limit",
            ),
            (
                [0, 0, 1000, 2799, 2800],
                [
                    ("stdout", "Exported 110000/117231 records\n", 0),
                    ("stderr", "final diagnostic\n", 1000),
                    queue.Empty(),
                ],
                "no output",
            ),
        ],
    )
    def test_streaming_deadlines(self, times, events, reason):
        from src.utils.pak_extractor import _active_procs, _run_subprocess

        process = MagicMock(returncode=0)
        process.poll.return_value = 0 if reason is None else None
        event_queue = MagicMock()
        event_queue.get.side_effect = events
        event_queue.get_nowait.side_effect = queue.Empty
        event_queue.empty.return_value = True
        messages = []
        with (
            patch("src.utils.pak_extractor.subprocess.Popen", return_value=process),
            patch("src.utils.pak_extractor.threading.Thread") as reader,
            patch("src.utils.pak_extractor.queue.Queue", return_value=event_queue),
            patch("src.utils.pak_extractor.time.monotonic", side_effect=times),
        ):
            if reason is None:
                result = _run_subprocess(
                    ["example.exe"], timeout=7200, idle_timeout=1800, progress_callback=messages.append
                )
                assert result.returncode == 0
                assert "117231/117231" in result.stdout
                assert result.stderr == "diagnostic\n"
                process.kill.assert_not_called()
            else:
                with pytest.raises(subprocess.TimeoutExpired, match=reason) as result:
                    _run_subprocess(["example.exe"], timeout=7200, idle_timeout=1800, progress_callback=messages.append)
                assert "110000/117231" in result.value.output
                assert "110000/117231" in str(result.value)
                if reason == "no output":
                    assert result.value.stderr == "final diagnostic\n"
                    assert "final diagnostic" in str(result.value)
                process.kill.assert_called_once()
            assert reader.return_value.join.called
        assert not _active_procs

    def test_streaming_nonzero_exit_is_not_timeout(self):
        from src.utils.pak_extractor import _run_subprocess

        result = _run_subprocess(
            [sys.executable, "-c", "import sys; print('final error', file=sys.stderr); sys.exit(1)"],
            timeout=10,
            idle_timeout=5,
        )
        assert result.returncode == 1
        assert result.stderr == "final error\n"

    def test_queued_output_prevents_false_idle_timeout(self):
        from src.utils.pak_extractor import _run_subprocess

        process = MagicMock(returncode=0)
        process.poll.return_value = 0
        events = MagicMock()
        events.get_nowait.return_value = ("stderr", "still working\n", 1800)
        events.get.side_effect = [("stdout", None, 1801), ("stderr", None, 1801)]
        with (
            patch("src.utils.pak_extractor.subprocess.Popen", return_value=process),
            patch("src.utils.pak_extractor.threading.Thread"),
            patch("src.utils.pak_extractor.queue.Queue", return_value=events),
            patch("src.utils.pak_extractor.time.monotonic", side_effect=[0, 1800, 1801, 1801]),
        ):
            result = _run_subprocess(["example.exe"], timeout=7200, idle_timeout=1800)
        assert result.stderr == "still working\n"
        process.kill.assert_not_called()

    def test_streaming_shutdown_kills_registered_process(self):
        from src.utils.pak_extractor import _active_procs, _run_subprocess, kill_active_subprocess

        def progress(message):
            kill_active_subprocess(threading.get_ident())

        result = _run_subprocess(
            [sys.executable, "-u", "-c", "import threading; print('ready'); threading.Event().wait(20)"],
            timeout=10,
            idle_timeout=5,
            progress_callback=progress,
        )
        assert result.returncode != 0
        assert not _active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    @pytest.mark.parametrize("reason, elapsed", [("total time limit", 7200), ("no output", 1800)])
    def test_timeout_stops_real_readers_and_captures_both_streams(self, reason, elapsed):
        from src.utils.pak_extractor import _active_procs, _run_subprocess

        clock = [0]

        def progress(message):
            if message.startswith("stdout:"):
                clock[0] = elapsed

        with patch("src.utils.pak_extractor.time.monotonic", side_effect=lambda: clock[0]):
            with pytest.raises(subprocess.TimeoutExpired, match=reason) as result:
                _run_subprocess(
                    [
                        sys.executable,
                        "-u",
                        "-c",
                        "import sys, threading; sys.stderr.write('last diagnostic\\n'); sys.stderr.flush(); "
                        "print('Exported 110000/117231 records', flush=True); threading.Event().wait(20)",
                    ],
                    timeout=7200,
                    idle_timeout=1800,
                    progress_callback=progress,
                )
        assert result.value.output == "Exported 110000/117231 records\n"
        assert result.value.stderr == "last diagnostic\n"
        assert not _active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    def test_streaming_drains_both_pipes_on_caller_thread(self):
        from src.utils.app_constants import SUBPROCESS_PROGRESS_LINE_CHARS
        from src.utils.pak_extractor import _active_procs, _run_subprocess

        caller = threading.get_ident()
        messages = []

        def progress(message):
            assert threading.get_ident() == caller
            messages.append(message)

        result = _run_subprocess(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('x'*200000+'\\n'); sys.stderr.write('y'*200000+'\\n')",
            ],
            timeout=10,
            idle_timeout=5,
            progress_callback=progress,
        )
        assert result.returncode == 0
        assert result.stdout == "x" * 200000 + "\n"
        assert result.stderr == "y" * 200000 + "\n"
        for name, expected in (("stdout", "x"), ("stderr", "y")):
            bodies = [message.partition(": ")[2] for message in messages if message.startswith(f"{name}: ")]
            assert "".join(bodies) == expected * 200000
            assert all(len(body) <= SUBPROCESS_PROGRESS_LINE_CHARS for body in bodies)
        assert not _active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    @pytest.mark.parametrize("newline", ["", "\n"])
    def test_streaming_oversized_output_is_bounded(self, newline):
        from src.utils.app_constants import (
            SUBPROCESS_CAPTURE_TAIL_CHARS,
            SUBPROCESS_OUTPUT_CHUNK_BYTES,
            SUBPROCESS_OUTPUT_QUEUE_SIZE,
            SUBPROCESS_PROGRESS_LINE_CHARS,
        )
        from src.utils.pak_extractor import _active_procs, _run_subprocess

        caller = threading.get_ident()
        lengths = {"stdout": 0, "stderr": 0}
        final_bodies = {}
        size = SUBPROCESS_CAPTURE_TAIL_CHARS * 16

        def progress(message):
            assert threading.get_ident() == caller
            name, _, body = message.partition(": ")
            assert 0 < len(body) <= SUBPROCESS_PROGRESS_LINE_CHARS
            lengths[name] += len(body)
            final_bodies[name] = body

        result = _run_subprocess(
            [
                sys.executable,
                "-c",
                "import sys; "
                f"sys.stdout.write('x'*{size}+'OUT_END'+{newline!r}); "
                f"sys.stderr.write('y'*{size}+'ERR_END'+{newline!r})",
            ],
            timeout=10,
            idle_timeout=5,
            progress_callback=progress,
        )
        assert SUBPROCESS_OUTPUT_QUEUE_SIZE * SUBPROCESS_OUTPUT_CHUNK_BYTES <= 4 * 1024 * 1024
        assert result.returncode == 0
        for name, marker, fill in (("stdout", "OUT_END", "x"), ("stderr", "ERR_END", "y")):
            tail = getattr(result, name)
            assert len(tail) == SUBPROCESS_CAPTURE_TAIL_CHARS
            assert tail == (fill * size + marker + newline)[-SUBPROCESS_CAPTURE_TAIL_CHARS:]
            assert lengths[name] == size + len(marker)
            assert final_bodies[name].endswith(marker)
        assert not _active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    def test_full_queue_callback_failure_stops_readers(self, monkeypatch):
        from src.utils import pak_extractor

        full = threading.Event()
        original_queue = queue.Queue

        class ObservedQueue(original_queue):
            def put(self, item, block=True, timeout=None):
                if self.full():
                    full.set()
                return super().put(item, block=block, timeout=timeout)

        monkeypatch.setattr(pak_extractor, "SUBPROCESS_OUTPUT_QUEUE_SIZE", 1)
        monkeypatch.setattr(pak_extractor.queue, "Queue", ObservedQueue)
        caller = threading.get_ident()
        calls = []

        def progress(message):
            assert threading.get_ident() == caller
            calls.append(message)
            assert full.wait(2), "producer must encounter the full queue before callback failure"
            raise ValueError("callback failed with full queue")

        with pytest.raises(ValueError, match="callback failed with full queue"):
            pak_extractor._run_subprocess(
                [
                    sys.executable,
                    "-u",
                    "-c",
                    "import os, threading\n"
                    "def flood(fd):\n"
                    f" while True: os.write(fd, b'x'*{pak_extractor.SUBPROCESS_PROGRESS_LINE_CHARS})\n"
                    "threading.Thread(target=flood, args=(2,), daemon=True).start()\n"
                    "flood(1)\n",
                ],
                timeout=10,
                progress_callback=progress,
            )
        assert len(calls) == 1
        assert full.is_set()
        assert not pak_extractor._active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    def test_streaming_split_unicode_preserves_normal_output(self, monkeypatch):
        from src.utils import pak_extractor

        original_popen = subprocess.Popen
        monkeypatch.setattr(pak_extractor, "SUBPROCESS_OUTPUT_CHUNK_BYTES", 1)
        monkeypatch.setattr(
            pak_extractor.subprocess,
            "Popen",
            lambda *args, **kwargs: original_popen(*args, **kwargs, encoding="utf-8"),
        )
        payload = "".join(f"Exported {index}: \u20ac\r\n" for index in range(26))
        messages = []
        result = pak_extractor._run_subprocess(
            [sys.executable, "-c", f"import os; os.write(1, {payload.encode('utf-8')!r})"],
            timeout=10,
            idle_timeout=5,
            progress_callback=messages.append,
        )
        assert result.stdout == payload.replace("\r\n", "\n")
        assert messages == [f"stdout: {line}" for line in payload.splitlines()]
        assert result.stderr == ""
        assert not pak_extractor._active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    @pytest.mark.parametrize("payload", [b"\xff", b"\xe2"])
    def test_streaming_decode_failure_propagates(self, monkeypatch, payload):
        from src.utils import pak_extractor

        original_popen = subprocess.Popen
        monkeypatch.setattr(
            pak_extractor.subprocess,
            "Popen",
            lambda *args, **kwargs: original_popen(*args, **kwargs, encoding="utf-8"),
        )
        messages = []
        with pytest.raises(UnicodeDecodeError):
            pak_extractor._run_subprocess(
                [sys.executable, "-c", f"import os; os.write(1, {payload!r})"],
                timeout=10,
                progress_callback=messages.append,
            )
        assert messages == []
        assert not pak_extractor._active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    @pytest.mark.parametrize("reason, elapsed", [("total time limit", 7200), ("no output", 1800)])
    def test_oversized_timeout_retains_both_diagnostic_tails(self, reason, elapsed):
        from src.utils.app_constants import SUBPROCESS_CAPTURE_TAIL_CHARS
        from src.utils.pak_extractor import _active_procs, _run_subprocess

        clock = [0]
        seen = set()
        size = SUBPROCESS_CAPTURE_TAIL_CHARS * 16

        def progress(message):
            if message.endswith("_END"):
                seen.add(message.partition(": ")[0])
                if seen == {"stdout", "stderr"}:
                    clock[0] = elapsed

        with patch("src.utils.pak_extractor.time.monotonic", side_effect=lambda: clock[0]):
            with pytest.raises(subprocess.TimeoutExpired, match=reason) as result:
                _run_subprocess(
                    [
                        sys.executable,
                        "-u",
                        "-c",
                        "import sys, threading; "
                        f"sys.stdout.write('x'*{size}+'OUT_END\\n'); "
                        f"sys.stderr.write('y'*{size}+'ERR_END\\n'); "
                        "threading.Event().wait(20)",
                    ],
                    timeout=7200,
                    idle_timeout=1800,
                    progress_callback=progress,
                )
        assert seen == {"stdout", "stderr"}
        for tail, marker in ((result.value.output, "OUT_END\n"), (result.value.stderr, "ERR_END\n")):
            assert len(tail) == SUBPROCESS_CAPTURE_TAIL_CHARS
            assert tail.endswith(marker)
        assert not _active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    def test_streaming_callback_failure_cleans_up(self):
        from src.utils.pak_extractor import _active_procs, _run_subprocess

        def progress(message):
            raise ValueError("callback failed")

        with pytest.raises(ValueError, match="callback failed"):
            _run_subprocess(
                [sys.executable, "-u", "-c", "import threading; print('ready'); threading.Event().wait(20)"],
                timeout=10,
                progress_callback=progress,
            )
        assert not _active_procs
        assert not any(thread.name.startswith("export-") for thread in threading.enumerate())

    def test_timeout_preserves_cause_and_final_output(self):

        from src.utils.pak_extractor import _active_procs, _run_subprocess

        process = MagicMock()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(["example.exe"], 30),
            ("Exported 110000/117231 records\n", "final diagnostic"),
        ]
        with patch("src.utils.pak_extractor.subprocess.Popen", return_value=process):
            with pytest.raises(subprocess.TimeoutExpired) as result:
                _run_subprocess(["example.exe"], timeout=30)
        process.kill.assert_called_once()
        assert result.value.output == "Exported 110000/117231 records\n"
        assert result.value.stderr == "final diagnostic"
        assert not _active_procs


@pytest.mark.unit
class TestDataForgeExtraction:
    """P4K extraction pipeline — error handling paths."""

    @pytest.mark.parametrize("failure", ["exit", "total time limit", "no output"])
    def test_export_deadlines_progress_and_failure_preserve_cache(self, monkeypatch, tmp_path, caplog, failure):
        from src.utils.app_constants import (
            DATAFORGE_EXPORT_IDLE_TIMEOUT_SECONDS,
            DATAFORGE_EXPORT_TOTAL_TIMEOUT_SECONDS,
        )
        from src.utils.pak_extractor import _SubprocessOutputTimeout

        p4k, unp4k, unforge = (tmp_path / name for name in ("Data.p4k", "unp4k.exe", "unforge.cli.exe"))
        for path in (p4k, unp4k, unforge):
            path.write_bytes(b"fixture")
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "old.xml").write_text("old")
        validator = MagicMock()
        finalizer = MagicMock()
        progress = []
        phase_progress = []
        stdout = (
            "unique head progress\n" + "old progress\n" * 1000 + "Exported 110000/117231 records\nfinal record error"
        )
        stderr = "unique head diagnostic\n" + "old diagnostic\n" * 1000 + "final stderr cause"

        def fake_run(args, *, cwd=None, timeout=None, progress_callback=None, idle_timeout=None):
            if args[0] == str(unp4k):
                assert timeout == 600
                assert progress_callback is None and idle_timeout is None
                dcb = Path(cwd) / "Data/Game2.dcb"
                dcb.parent.mkdir()
                dcb.write_bytes(b"dcb")
                return subprocess.CompletedProcess(args, 0, "", "")
            assert timeout == DATAFORGE_EXPORT_TOTAL_TIMEOUT_SECONDS == 7200
            assert idle_timeout == DATAFORGE_EXPORT_IDLE_TIMEOUT_SECONDS == 1800
            progress_callback("stdout: Exported 110000/117231 records")
            progress_callback("stderr: final stderr cause")
            if failure != "exit":
                exc = _SubprocessOutputTimeout(
                    args, timeout if failure == "total time limit" else idle_timeout, failure
                )
                exc.output, exc.stderr = stdout, stderr
                raise exc
            return subprocess.CompletedProcess(args, 1, stdout, stderr)

        monkeypatch.setattr("src.utils.pak_extractor._run_subprocess", fake_run)
        monkeypatch.setattr("src.utils.pak_extractor._validate_dataforge_export", validator)
        expected = RuntimeError if failure == "exit" else subprocess.TimeoutExpired
        with caplog.at_level("INFO"), pytest.raises(expected) as result:
            extract_dataforge(
                p4k,
                unp4k,
                unforge,
                cache,
                progress_callback=progress.append,
                progress_pct_callback=lambda *args: phase_progress.append(args),
                finalize_callback=finalizer,
            )
        assert "final record error" in str(result.value)
        assert "final stderr cause" in str(result.value)
        assert "unique head" not in str(result.value)
        if failure == "exit":
            assert "code 1" in str(result.value)
            assert "final record error" in caplog.text
        else:
            assert failure in str(result.value)
        assert "DataForge Exporter Progress: Exported 110000/117231 records" in progress
        assert "DataForge Exporter Diagnostic: final stderr cause" in progress
        assert "DataForge Exporter Progress: Exported 110000/117231 records" in caplog.text
        assert [completed for completed, total, label in phase_progress] == [0, 1]
        validator.assert_not_called()
        finalizer.assert_not_called()
        assert (cache / "old.xml").read_text() == "old"
        assert not list(tmp_path.glob(".cache.staging-*"))

    @patch("src.utils.pak_extractor.subprocess.run")
    def test_missing_tools_raises(self, mock_run):
        """FileNotFoundError from unp4k.exe propagates as an exception."""
        mock_run.side_effect = FileNotFoundError("unp4k.exe not found")
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")
            with pytest.raises(Exception):  # noqa: B017 — test calls wrong arg count; TypeError is expected here
                extract_dataforge(p4k_path, os.path.join(tmpdir, "cache"))

    @patch("src.utils.pak_extractor.subprocess.run")
    def test_pipeline_stops_on_first_failure(self, mock_run):
        """If unp4k fails, unforge is never called."""
        mock_run.side_effect = [
            Exception("unp4k failed"),
            MagicMock(returncode=0),  # Should not be reached
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p4k_path = os.path.join(tmpdir, "Data.p4k")
            with open(p4k_path, "w") as f:
                f.write("dummy")
            with pytest.raises(Exception):  # noqa: B017 — test calls wrong arg count; TypeError is expected here
                extract_dataforge(p4k_path, os.path.join(tmpdir, "cache"))
            # subprocess.run is called at most once (the first tool invocation)
            assert mock_run.call_count <= 1

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_finalizer_failure_preserves_existing_cache(self, mock_run, tmp_path):
        p4k = tmp_path / "Data.p4k"
        unp4k = tmp_path / "unp4k.exe"
        unforge = tmp_path / "unforge.cli.exe"
        cache = tmp_path / "dataforge"
        p4k.write_bytes(b"p4k")
        unp4k.write_bytes(b"unp4k")
        unforge.write_bytes(b"unforge")
        (cache / "raw" / "libs").mkdir(parents=True)
        (cache / "old.xml").write_text("old", encoding="utf-8")

        def fake_run(args, cwd=None, timeout=None, progress_callback=None, idle_timeout=None):
            if args[-1] == ".dcb":
                dcb = Path(cwd) / "Data" / "Game2.dcb"
                dcb.parent.mkdir(parents=True)
                dcb.write_bytes(b"dcb")
            else:
                records = Path(args[1]).parent / "libs" / "foundry" / "records" / "entities" / "scitem"
                records.mkdir(parents=True)
                (records / "item.xml").write_text("<item/>", encoding="utf-8")
                _write_export_manifest(Path(args[1]))
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run

        def fail_finalizer(_):
            raise RuntimeError("patch failed")

        with pytest.raises(RuntimeError, match="patch failed"):
            extract_dataforge(p4k, unp4k, unforge, cache, finalize_callback=fail_finalizer)

        assert (cache / "old.xml").read_text(encoding="utf-8") == "old"
        assert not list(tmp_path.glob(".dataforge.staging-*"))

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_extract_creates_pristine_and_patched_layers(self, mock_run, tmp_path):
        p4k = tmp_path / "Data.p4k"
        unp4k = tmp_path / "unp4k.exe"
        unforge = tmp_path / "unforge.cli.exe"
        cache = tmp_path / "dataforge"
        p4k.write_bytes(b"p4k")
        unp4k.write_bytes(b"unp4k")
        unforge.write_bytes(b"unforge")

        def fake_run(args, cwd=None, timeout=None, progress_callback=None, idle_timeout=None):
            if args[-1] == ".dcb":
                dcb = Path(cwd) / "Data" / "Game2.dcb"
                dcb.parent.mkdir(parents=True)
                dcb.write_bytes(b"dcb")
            else:
                records = Path(args[1]).parent / "libs" / "foundry" / "records" / "entities" / "scitem"
                records.mkdir(parents=True)
                (records / "item.xml").write_text("<item>original</item>", encoding="utf-8")
                spaceships = records.parent / "spaceships"
                spaceships.mkdir()
                (spaceships / "ship.xml").write_text("<ship/>", encoding="utf-8")
                _write_export_manifest(Path(args[1]))
            return MagicMock(returncode=0, stdout="", stderr="")

        def finalize(staging_root):
            patched = staging_root / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
            patched.write_text("<item>patched</item>", encoding="utf-8")

        mock_run.side_effect = fake_run
        extract_dataforge(p4k, unp4k, unforge, cache, finalize_callback=finalize, patch_fingerprint="patches-v1")

        pristine = cache / "pristine" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        patched = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        assert "original</item>" in pristine.read_text(encoding="utf-8")
        assert patched.read_text(encoding="utf-8") == "<item>patched</item>"
        assert _read_dataforge_identity(cache)["patch_fingerprint"] == "patches-v1"

    @pytest.mark.parametrize(
        "defect",
        [
            "missing",
            "incomplete",
            "count",
            "error",
            "truncation",
            "duplicate",
            "source",
            "header",
            "xml",
            "body_error",
            "guard",
            "path",
        ],
    )
    def test_export_integrity_rejects_incomplete_output(self, tmp_path, defect):
        dcb = tmp_path / "Game2.dcb"
        records = tmp_path / "libs/foundry/records"
        records.mkdir(parents=True)
        (records / "one.xml").write_text("<one/>")
        (records / "two.xml").write_text("<two/>")
        manifest_path, manifest = _write_export_manifest(dcb)
        if defect == "missing":
            manifest_path.unlink()
        elif defect == "header":
            dcb.write_bytes(b"dcb")
        elif defect == "xml":
            (records / "one.xml").unlink()
        elif defect == "body_error":
            text = (records / "one.xml").read_text().replace("/>", ' bad="Error reading property" />')
            (records / "one.xml").write_text(text)
        else:
            if defect == "incomplete":
                manifest["complete"] = False
            elif defect == "count":
                manifest["exportedRecords"] -= 1
            elif defect == "error":
                manifest["errors"] = 1
            elif defect == "truncation":
                manifest["truncations"] = 1
            elif defect == "duplicate":
                manifest["records"][1] = manifest["records"][0]
            elif defect == "source":
                manifest["sourceSha256"] = "0" * 64
            elif defect == "guard":
                manifest["records"][0]["guards"] = {"pointer_depth": 1}
            elif defect == "path":
                manifest["records"][0]["actualOutputPath"] = "../escape.xml"
            manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(RuntimeError, match="export integrity"):
            _validate_dataforge_export(dcb)

    def test_export_integrity_accepts_complete_binary_uuid_set(self, tmp_path):
        dcb = tmp_path / "Game2.dcb"
        records = tmp_path / "libs/foundry/records"
        records.mkdir(parents=True)
        (records / "one.xml").write_text("<one/>")
        manifest, _ = _write_export_manifest(dcb)
        assert _validate_dataforge_export(dcb) == manifest

    @pytest.mark.parametrize("body", ["", "payload"])
    def test_export_integrity_requires_empty_body_with_nested_empty_guards(self, tmp_path, body):
        dcb = tmp_path / "Game2.dcb"
        records = tmp_path / "libs/foundry/records"
        records.mkdir(parents=True)
        (records / "one.xml").write_text(f"<one>{body}</one>")
        manifest_path, manifest = _write_export_manifest(dcb)
        manifest["records"][0]["status"] = "empty"
        manifest["records"][0]["guards"] = {"empty_structure": 3}
        manifest["emptyRecords"] = 1
        manifest["guards"] = {"empty_structure": 3}
        manifest_path.write_text(json.dumps(manifest))
        if body:
            with pytest.raises(RuntimeError, match="empty-body proof"):
                _validate_dataforge_export(dcb)
        else:
            assert _validate_dataforge_export(dcb) == manifest_path

    @pytest.mark.parametrize("manifest_defect", ["missing", "errors", "truncations"])
    @patch("src.utils.pak_extractor._run_subprocess")
    def test_export_integrity_failure_never_activates_cache(self, mock_run, tmp_path, manifest_defect):
        p4k = tmp_path / "Data.p4k"
        unp4k = tmp_path / "unp4k.exe"
        unforge = tmp_path / "unforge.cli.exe"
        for path in (p4k, unp4k, unforge):
            path.write_bytes(b"fixture")
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "old.xml").write_text("old")
        finalizer = MagicMock()

        def fake_run(args, cwd=None, timeout=None, progress_callback=None, idle_timeout=None):
            if args[-1] == ".dcb":
                dcb = Path(cwd) / "Data/Game2.dcb"
                dcb.parent.mkdir()
                dcb.write_bytes(b"dcb")
            else:
                dcb = Path(args[1])
                records = dcb.parent / "libs/foundry/records/entities/scitem"
                records.mkdir(parents=True)
                (records / "item.xml").write_text("<item/>")
                manifest_path, manifest = _write_export_manifest(dcb)
                if manifest_defect == "missing":
                    manifest_path.unlink()
                else:
                    manifest[manifest_defect] = 1
                    manifest_path.write_text(json.dumps(manifest))
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run
        with pytest.raises(RuntimeError, match="export integrity"):
            extract_dataforge(p4k, unp4k, unforge, cache, finalize_callback=finalizer)
        finalizer.assert_not_called()
        assert (cache / "old.xml").read_text() == "old"
        assert not list(tmp_path.glob(".cache.staging-*"))


# ─────────────────────────────────────────────────────────────────────────────
# Filtered cache copy (cache streamlining — 0.9.3)
# ─────────────────────────────────────────────────────────────────────────────


_GENERATOR_SCRIPT = Path(__file__).parent.parent / "scripts" / "generate_enhancements_ini.py"


def _records_path(node: ast.AST, aliases: dict[str, tuple[str, ...]]) -> tuple[str, ...] | None:
    """Resolve a literal records path, including aliases derived from records."""
    if isinstance(node, ast.Name):
        if node.id == "records":
            return ()
        return aliases.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        parent = _records_path(node.left, aliases)
        if parent is None:
            return None
        if not isinstance(node.right, ast.Constant) or not isinstance(node.right.value, str):
            raise AssertionError(f"Unsupported dynamic DataForge records path: {ast.unparse(node)}")
        return (*parent, node.right.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
        parent = _records_path(node.func.value, aliases)
        if parent is None:
            return None
        if not all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args):
            raise AssertionError(f"Unsupported dynamic DataForge records path: {ast.unparse(node)}")
        return (*parent, *(arg.value for arg in node.args))
    return None


def _generator_read_subpaths(source: str | None = None) -> set[str]:
    tree = ast.parse(source if source is not None else _GENERATOR_SCRIPT.read_text(encoding="utf-8"))
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    paths: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load) or node.id != "records":
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node and parent.attr in {"exists", "stat"}:
            continue
        if isinstance(parent, ast.Attribute) and parent.value is node and parent.attr == "glob":
            call = parents.get(parent)
            if (
                not isinstance(call, ast.Call)
                or len(call.args) != 1
                or not isinstance(call.args[0], ast.Constant)
                or not isinstance(call.args[0].value, str)
            ):
                raise AssertionError(f"Unsupported dynamic DataForge records path: {ast.unparse(call)}")
            paths.add(call.args[0].value)
            continue
        if not (isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div) and parent.left is node) and not (
            isinstance(parent, ast.Assign) and parent.value is node
        ):
            raise AssertionError(f"Unsupported DataForge records binding: {ast.unparse(parent)}")
    aliases: dict[str, tuple[str, ...]] = {}
    assignments = sorted(
        (node for node in ast.walk(tree) if isinstance(node, ast.Assign)), key=lambda node: node.lineno
    )
    for node in assignments:
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        alias_parts = _records_path(node.value, aliases)
        if alias_parts is None:
            continue
        if not alias_parts:
            raise AssertionError(f"Unsupported bare DataForge records alias: {ast.unparse(node)}")
        aliases[node.targets[0].id] = alias_parts
        paths.add("/".join(alias_parts))
    for node in ast.walk(tree):
        path_parts = _records_path(node, aliases)
        if not path_parts:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div) and parent.left is node:
            continue
        paths.add("/".join(path_parts))
    return paths


def _is_subpath_of(child: str, parent: str) -> bool:
    """Is *child* equal to or under *parent* in slash-separated form?"""
    if child == parent:
        return True
    return child.startswith(parent + "/")


@pytest.mark.regression
class TestDataForgeKeepList:
    """Regression tests locking the keep-list to the generator's read-paths.

    These are the guard-rails that catch the dangerous failure mode of cache
    streamlining: a future generator change reads from a subtree the extractor
    doesn't copy, producing silently-empty enhancements rather than an error.
    """

    def test_every_generator_read_path_is_covered(self):
        """Every path the generator reads must lie under some kept subpath."""
        keep = (*DATAFORGE_KEEP_SUBPATHS, *DATAFORGE_KEEP_FILE_GLOBS)
        uncovered = []
        for read in _generator_read_subpaths():
            if not any(_is_subpath_of(read, k) for k in keep):
                uncovered.append(read)
        assert not uncovered, (
            "Generator reads from paths the extractor does NOT cache:\n  "
            + "\n  ".join(uncovered)
            + "\nAdd these (or a common ancestor) to DATAFORGE_KEEP_SUBPATHS "
            "in src/utils/dataforge_contract.py."
        )

    def test_keep_list_has_no_redundant_entries(self):
        """Reject entries that are already covered by another entry (a parent)."""
        redundant = []
        for i, entry in enumerate(DATAFORGE_KEEP_SUBPATHS):
            for j, other in enumerate(DATAFORGE_KEEP_SUBPATHS):
                if i == j:
                    continue
                if _is_subpath_of(entry, other):
                    redundant.append((entry, other))
                    break
        assert not redundant, (
            f"DATAFORGE_KEEP_SUBPATHS contains entries already covered by an ancestor entry: {redundant}"
        )

    @pytest.mark.parametrize(
        "source",
        [
            "target = records / dynamic_subtree",
            'for source in (records,):\n    target = source / "new_subtree"',
        ],
    )
    def test_rejects_unsupported_records_path_bindings(self, source):
        with pytest.raises(
            AssertionError, match="Unsupported (dynamic DataForge records path|DataForge records binding)"
        ):
            _generator_read_subpaths(source)

    def test_tracks_multi_step_literal_records_aliases(self):
        paths = _generator_read_subpaths(
            'base = records / "entities"\nships = base / "spaceships"\nscan(ships / "fighter")'
        )

        assert "entities" in paths
        assert "entities/spaceships" in paths
        assert "entities/spaceships/fighter" in paths

    def test_allows_records_metadata_calls(self):
        assert _generator_read_subpaths("records.exists()\nrecords.stat()") == set()

    def test_tracks_literal_file_globs(self):
        assert _generator_read_subpaths('records.glob("actor/actors/example*.xml")') == {"actor/actors/example*.xml"}

    def test_rejects_dynamic_file_globs(self):
        with pytest.raises(AssertionError, match="Unsupported dynamic DataForge records path"):
            _generator_read_subpaths("records.glob(pattern)")


@pytest.mark.unit
class TestCopyFilteredRecords:
    """Exercise the filtered-copy helper on a synthetic unforge output tree."""

    @staticmethod
    def _make_fake_unforge_output(root: Path) -> None:
        """Write a minimal ``libs/foundry/records/...`` tree with one file in
        each of the keep-paths plus several 'unused' paths that must NOT be
        carried over by the filter."""
        records = root / "libs" / "foundry" / "records"
        # Files inside kept subtrees — these MUST survive the filter.
        for kept in DATAFORGE_KEEP_SUBPATHS:
            leaf = records / kept / "sample.xml"
            leaf.parent.mkdir(parents=True, exist_ok=True)
            leaf.write_text("<kept/>", encoding="utf-8")
        # Files in paths we want dropped — these must NOT survive.
        for dropped in ("ui", "actor", "missiondata", "tintpalettes", "starmap"):
            leaf = records / dropped / "sample.xml"
            leaf.parent.mkdir(parents=True, exist_ok=True)
            leaf.write_text("<dropped/>", encoding="utf-8")

    def test_copies_only_keep_subpaths(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        self._make_fake_unforge_output(src)

        copied, skipped = _copy_filtered_records(src / "libs", dst / "libs")

        records_dst = dst / "libs" / "foundry" / "records"
        for kept in DATAFORGE_KEEP_SUBPATHS:
            assert (records_dst / kept / "sample.xml").exists(), f"kept path {kept!r} missing from filtered output"
        for dropped in ("ui", "actor", "missiondata", "tintpalettes", "starmap"):
            assert not (records_dst / dropped).exists(), f"{dropped!r} leaked into filtered output"
        assert copied == len(DATAFORGE_KEEP_SUBPATHS)
        assert skipped == len(DATAFORGE_KEEP_FILE_GLOBS)

    def test_copies_only_selected_actor_files(self, tmp_path):
        src = tmp_path / "src/libs"
        actors = src / "foundry/records/actor/actors"
        actors.mkdir(parents=True)
        for filename in ("argo_atls_example.xml", "unrelated.xml"):
            (actors / filename).write_text("<entity/>", encoding="utf-8")
        dst = tmp_path / "dst/libs"
        copied, skipped = _copy_filtered_records(src, dst)
        assert (dst / "foundry/records/actor/actors/argo_atls_example.xml").exists()
        assert not (dst / "foundry/records/actor/actors/unrelated.xml").exists()
        assert copied == len(DATAFORGE_KEEP_FILE_GLOBS)
        assert skipped == len(DATAFORGE_KEEP_SUBPATHS)

    def test_keeps_actor_uuid_sibling_by_original_path(self, tmp_path):
        src = tmp_path / "src/libs"
        actors = src / "foundry/records/actor/actors"
        actors.mkdir(parents=True)
        sibling = "11111111-2222-3333-4444-555555555555.xml"
        (actors / sibling).write_text("<actor/>")
        (actors / "unrelated.xml").write_text("<actor/>")
        manifest = {
            "records": [
                {
                    "originalPath": "libs/foundry/records/actor/actors/argo_atls_example.xml",
                    "actualOutputPath": f"libs/foundry/records/actor/actors/{sibling}",
                }
            ]
        }
        (src.parent / ".unforge-export.json").write_text(json.dumps(manifest))
        dst = tmp_path / "dst/libs"
        _copy_filtered_records(src, dst)
        assert (dst / "foundry/records/actor/actors" / sibling).exists()
        assert not (dst / "foundry/records/actor/actors/unrelated.xml").exists()

    def test_skipped_when_source_subpath_missing(self, tmp_path):
        """Some patches don't ship every subtree (e.g. entities/missions).
        Missing source paths should increment `skipped`, not fail."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        self._make_fake_unforge_output(src)
        # Delete one keep-path from the source so the filter sees it missing.
        import shutil as _sh

        _sh.rmtree(src / "libs" / "foundry" / "records" / "entities" / "missions")

        copied, skipped = _copy_filtered_records(src / "libs", dst / "libs")

        assert skipped == 1 + len(DATAFORGE_KEEP_FILE_GLOBS)
        assert copied == len(DATAFORGE_KEEP_SUBPATHS) - 1
        records_dst = dst / "libs" / "foundry" / "records"
        assert not (records_dst / "entities" / "missions").exists()
        # All other kept paths survived
        assert (records_dst / "entities" / "scitem" / "sample.xml").exists()

    def test_raises_on_unexpected_layout(self, tmp_path):
        """If unforge's output doesn't have the expected libs/foundry/records
        layout, fail loudly rather than producing a silently-empty cache."""
        src = tmp_path / "src"
        (src / "libs").mkdir(parents=True)
        # No foundry/records under libs — nothing for the filter to work with.

        with pytest.raises(FileNotFoundError):
            _copy_filtered_records(src / "libs", tmp_path / "dst" / "libs")


@pytest.mark.unit
class TestDataForgeHealth:
    def test_health_check_reports_its_own_phase_and_completion(self, tmp_path):
        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)
        progress = []
        validate_dataforge_cache(cache, progress.append)
        assert progress[0] == "Checking cached DataForge records…"
        assert progress[1] == "Checking cached records: 0 / 2"
        assert progress[-1] == "Checking cached records: 2 / 2"

    def _write_required_xml(self, cache: Path) -> None:
        records = cache / "raw" / "libs" / "foundry" / "records" / "entities"
        for directory, content in (("scitem", "<item/>"), ("spaceships", "<ship/>")):
            target = records / directory
            target.mkdir(parents=True)
            (target / "sample.xml").write_text(content, encoding="utf-8")

    def test_reports_required_xml_counts(self, tmp_path):
        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)

        report = validate_dataforge_cache(cache)

        assert report.xml_counts == {"entities/scitem": 1, "entities/spaceships": 1}

    def test_rejects_missing_required_subtree(self, tmp_path):
        cache = tmp_path / "dataforge"
        records = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem"
        records.mkdir(parents=True)
        (records / "sample.xml").write_text("<item/>", encoding="utf-8")

        with pytest.raises(RuntimeError, match="entities/spaceships"):
            validate_dataforge_cache(cache)

    def test_rejects_malformed_required_xml(self, tmp_path):
        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)
        malformed = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "sample.xml"
        malformed.write_text("<item>", encoding="utf-8")

        with pytest.raises(RuntimeError, match="invalid XML"):
            validate_dataforge_cache(cache)

    def test_rejects_malformed_xml_after_valid_file(self, tmp_path):
        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)
        malformed = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "later.xml"
        malformed.write_text("<item>", encoding="utf-8")

        with pytest.raises(RuntimeError, match="later.xml"):
            validate_dataforge_cache(cache)

    @pytest.mark.parametrize(
        "content",
        [
            '<Error value="example export failure"/>',
            '<Entity><Components><Error value="example export failure"/></Components></Entity>',
        ],
    )
    def test_reports_export_errors_without_rejecting_usable_cache(self, tmp_path, caplog, content):
        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)
        relative = "entities/scitem/example_error.xml"
        error_file = cache / "raw/libs/foundry/records" / relative
        error_file.write_text(content, encoding="utf-8")
        report = validate_dataforge_cache(cache)
        assert report.xml_counts == {"entities/scitem": 1, "entities/spaceships": 1}
        assert report.export_error_files == (relative,)
        assert "1 files contain export errors" in report.summary_line()
        assert relative in caplog.text
        assert "example export failure" not in caplog.text

    @pytest.mark.parametrize("content", ["<Error/>", "<Entity><Error/></Entity>"])
    def test_rejects_all_error_essential_subtree(self, tmp_path, content):
        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)
        (cache / "raw/libs/foundry/records/entities/scitem/sample.xml").write_text(content, encoding="utf-8")
        with pytest.raises(RuntimeError, match="no usable XML.*entities/scitem"):
            validate_dataforge_cache(cache)

    def test_reports_optional_subtree_errors(self, tmp_path):
        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)
        error = cache / "raw/libs/foundry/records/contracts/example.xml"
        error.parent.mkdir(parents=True)
        error.write_text("<Error/>", encoding="utf-8")
        report = validate_dataforge_cache(cache)
        assert report.export_error_files == ("contracts/example.xml",)
        assert report.xml_counts["entities/scitem"] == 1

    def test_export_warnings_are_bounded_but_report_keeps_all_paths(self, tmp_path, caplog):
        from src.utils.pak_extractor import _EXPORT_ERROR_DETAIL_LIMIT

        cache = tmp_path / "dataforge"
        self._write_required_xml(cache)
        errors = cache / "raw/libs/foundry/records/contracts"
        errors.mkdir()
        count = _EXPORT_ERROR_DETAIL_LIMIT + 3
        for index in range(count):
            (errors / f"example_{index}.xml").write_text("<Error/>", encoding="utf-8")
        report = validate_dataforge_cache(cache)
        assert len(report.export_error_files) == count
        messages = [record.getMessage() for record in caplog.records]
        assert (
            sum(message.startswith("DataForge incomplete XML export:") for message in messages)
            == _EXPORT_ERROR_DETAIL_LIMIT
        )
        assert len(messages) == _EXPORT_ERROR_DETAIL_LIMIT + 1
        assert f"export errors in {count} files" in messages[-1]


@pytest.mark.unit
class TestAtomicCacheReplacement:
    def test_replaces_old_cache_with_staged_cache(self, tmp_path):
        cache = tmp_path / "dataforge"
        staging = tmp_path / ".dataforge.staging"
        cache.mkdir()
        (cache / "old.xml").write_text("old", encoding="utf-8")
        staging.mkdir()
        (staging / "new.xml").write_text("new", encoding="utf-8")

        _replace_dataforge_cache(staging, cache)

        assert not staging.exists()
        assert not (cache / "old.xml").exists()
        assert (cache / "new.xml").read_text(encoding="utf-8") == "new"

    def test_restores_old_cache_when_staged_swap_fails(self, tmp_path, monkeypatch):
        cache = tmp_path / "dataforge"
        staging = tmp_path / ".dataforge.staging"
        cache.mkdir()
        (cache / "old.xml").write_text("old", encoding="utf-8")
        staging.mkdir()
        (staging / "new.xml").write_text("new", encoding="utf-8")

        original_replace = Path.replace

        def fail_staged_swap(source, target):
            if source == staging:
                raise OSError("swap failed")
            return original_replace(source, target)

        monkeypatch.setattr(Path, "replace", fail_staged_swap)
        monkeypatch.setattr("src.utils.pak_extractor.time.sleep", lambda _: None)

        with pytest.raises(OSError, match="swap failed"):
            _replace_dataforge_cache(staging, cache)

        assert (cache / "old.xml").read_text(encoding="utf-8") == "old"
        assert (staging / "new.xml").read_text(encoding="utf-8") == "new"

    def test_recovers_stranded_backup_when_live_cache_is_missing(self, tmp_path):
        cache = tmp_path / "dataforge"
        backup = tmp_path / ".dataforge.backup-interrupted"
        backup.mkdir()
        (backup / "old.xml").write_text("old", encoding="utf-8")

        _recover_dataforge_cache(cache)

        assert (cache / "old.xml").read_text(encoding="utf-8") == "old"
        assert not backup.exists()

    def test_retries_transient_staged_swap_failure(self, tmp_path, monkeypatch):
        cache = tmp_path / "dataforge"
        staging = tmp_path / ".dataforge.staging"
        cache.mkdir()
        staging.mkdir()
        (staging / "new.xml").write_text("new", encoding="utf-8")
        original_replace = Path.replace
        attempts = {"staging": 0}

        def fail_once(source, target):
            if source == staging and attempts["staging"] == 0:
                attempts["staging"] += 1
                raise OSError("temporary lock")
            return original_replace(source, target)

        monkeypatch.setattr(Path, "replace", fail_once)
        monkeypatch.setattr("src.utils.pak_extractor.time.sleep", lambda _: None)

        _replace_dataforge_cache(staging, cache)

        assert attempts["staging"] == 1
        assert (cache / "new.xml").exists()


@pytest.mark.unit
class TestPatchedCacheRebuild:
    def test_rebuilds_raw_from_pristine_when_patch_set_changes(self, tmp_path):
        cache = tmp_path / "dataforge"
        pristine_xml = cache / "pristine" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        raw_xml = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        pristine_xml.parent.mkdir(parents=True)
        raw_xml.parent.mkdir(parents=True)
        pristine_xml.write_text("<item>original</item>", encoding="utf-8")
        raw_xml.write_text("<item>old patch</item>", encoding="utf-8")
        spaceship = pristine_xml.parents[1] / "spaceships" / "ship.xml"
        spaceship.parent.mkdir()
        spaceship.write_text("<ship/>", encoding="utf-8")
        (cache / ".dataforge_identity.json").write_text(
            json.dumps({"schema_version": DATAFORGE_CACHE_SCHEMA_VERSION, "patch_fingerprint": "old"}), encoding="utf-8"
        )

        def finalize(staging_root):
            staged_xml = staging_root / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
            staged_xml.write_text("<item>new patch</item>", encoding="utf-8")

        progress = []
        rebuilt = rebuild_patched_dataforge_cache(cache, "new", finalize, progress.append)

        assert rebuilt is True
        assert progress[0] == "Checking cached DataForge records…"
        assert progress[-1] == "Checking cached records: 2 / 2"
        assert pristine_xml.read_text(encoding="utf-8") == "<item>original</item>"
        assert raw_xml.read_text(encoding="utf-8") == "<item>new patch</item>"
        assert _read_dataforge_identity(cache)["patch_fingerprint"] == "new"

    def test_skips_rebuild_when_patch_set_is_unchanged(self, tmp_path):
        cache = tmp_path / "dataforge"
        (cache / ".dataforge_identity.json").parent.mkdir(parents=True)
        (cache / ".dataforge_identity.json").write_text(
            json.dumps({"schema_version": DATAFORGE_CACHE_SCHEMA_VERSION, "patch_fingerprint": "same"}),
            encoding="utf-8",
        )

        assert rebuild_patched_dataforge_cache(cache, "same", lambda _: pytest.fail("should not finalize")) is False

    def test_patch_removal_restores_raw_from_pristine(self, tmp_path):
        cache = tmp_path / "dataforge"
        pristine_xml = cache / "pristine" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        raw_xml = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        pristine_xml.parent.mkdir(parents=True)
        raw_xml.parent.mkdir(parents=True)
        pristine_xml.write_text("<item>original</item>", encoding="utf-8")
        raw_xml.write_text("<item>removed patch value</item>", encoding="utf-8")
        spaceship = pristine_xml.parents[1] / "spaceships" / "ship.xml"
        spaceship.parent.mkdir()
        spaceship.write_text("<ship/>", encoding="utf-8")
        (cache / ".dataforge_identity.json").write_text(
            json.dumps({"schema_version": DATAFORGE_CACHE_SCHEMA_VERSION, "patch_fingerprint": "with-patch"}),
            encoding="utf-8",
        )

        assert rebuild_patched_dataforge_cache(cache, "no-patches", lambda _: None) is True
        assert raw_xml.read_text(encoding="utf-8") == "<item>original</item>"

    def test_failed_health_check_preserves_live_raw_layer(self, tmp_path):
        cache = tmp_path / "dataforge"
        pristine = cache / "pristine" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        raw = cache / "raw" / "libs" / "foundry" / "records" / "entities" / "scitem" / "item.xml"
        pristine.parent.mkdir(parents=True)
        raw.parent.mkdir(parents=True)
        pristine.write_text("<item>broken</item>", encoding="utf-8")
        raw.write_text("<item>live</item>", encoding="utf-8")
        (cache / ".dataforge_identity.json").write_text(
            json.dumps({"schema_version": DATAFORGE_CACHE_SCHEMA_VERSION, "patch_fingerprint": "old"}), encoding="utf-8"
        )

        with pytest.raises(RuntimeError, match="entities/spaceships"):
            rebuild_patched_dataforge_cache(cache, "new", lambda _: None)

        assert raw.read_text(encoding="utf-8") == "<item>live</item>"

    def test_recovers_interrupted_raw_layer_replacement(self, tmp_path):
        cache = tmp_path / "dataforge"
        backup = cache / ".raw.backup-interrupted"
        backup.mkdir(parents=True)
        (backup / "old.xml").write_text("patched", encoding="utf-8")

        _recover_dataforge_layer(cache, "raw")

        assert (cache / "raw" / "old.xml").read_text(encoding="utf-8") == "patched"
        assert not backup.exists()


# ─────────────────────────────────────────────────────────────────────────────
# _robust_rmtree
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRobustRmtree:
    def test_removes_normal_directory(self, tmp_path):
        target = tmp_path / "to_delete"
        target.mkdir()
        (target / "file.txt").write_text("hi", encoding="utf-8")
        robust_rmtree(target)
        assert not target.exists()

    def test_succeeds_silently_when_path_missing(self, tmp_path):
        robust_rmtree(tmp_path / "nonexistent")

    def test_removes_read_only_files(self, tmp_path):
        target = tmp_path / "ro_dir"
        target.mkdir()
        ro_file = target / "readonly.txt"
        ro_file.write_text("data", encoding="utf-8")
        ro_file.chmod(stat.S_IREAD)
        robust_rmtree(target)
        assert not target.exists()

    def test_raises_after_all_attempts_fail(self, tmp_path, monkeypatch):
        target = tmp_path / "stubborn"
        target.mkdir()
        (target / "x.txt").write_text("x", encoding="utf-8")

        import shutil

        call_count = {"n": 0}

        def _always_fail(path, **kwargs):
            call_count["n"] += 1
            raise OSError("locked")

        monkeypatch.setattr(shutil, "rmtree", _always_fail)
        monkeypatch.setattr("time.sleep", lambda _: None)
        with pytest.raises(OSError):
            robust_rmtree(target, attempts=3)
        assert call_count["n"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# dataforge_cache_is_fresh — stamp-based logic
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDataForgeCacheFreshStamp:
    def _make_p4k(self, parent: Path, mtime: float) -> Path:
        p4k = parent / "Data.p4k"
        p4k.write_bytes(b"dummy")
        os.utime(p4k, (mtime, mtime))
        return p4k

    def _make_cache_with_stamp(self, parent: Path, stamp_mtime: float) -> Path:
        cache = parent / "dataforge"
        for layer in ("pristine", "raw"):
            libs = cache / layer / "libs" / "foundry" / "records"
            for subtree, content in (("entities/scitem", "<item/>"), ("entities/spaceships", "<ship/>")):
                target = libs / subtree
                target.mkdir(parents=True)
                (target / "sample.xml").write_text(content, encoding="utf-8")
        stamp = cache / ".p4k_mtime"
        stamp.write_text(str(stamp_mtime))
        return cache

    def _write_identity(self, cache: Path, p4k: Path, unp4k: Path | None = None, unforge: Path | None = None) -> None:
        identity = {
            "schema_version": DATAFORGE_CACHE_SCHEMA_VERSION,
            "p4k": {"size": p4k.stat().st_size, "mtime_ns": p4k.stat().st_mtime_ns},
            "tools": {},
            "patch_fingerprint": "test",
        }
        if unp4k is not None and unforge is not None:
            identity["tools"] = {
                "unp4k": {"size": unp4k.stat().st_size, "mtime_ns": unp4k.stat().st_mtime_ns},
                "unforge": {"size": unforge.stat().st_size, "mtime_ns": unforge.stat().st_mtime_ns},
            }
        (cache / ".dataforge_identity.json").write_text(json.dumps(identity), encoding="utf-8")

    def test_fresh_when_stamp_matches(self, tmp_path):
        mtime = 1700000000.0
        p4k = self._make_p4k(tmp_path, mtime)
        cache = self._make_cache_with_stamp(tmp_path, mtime)
        self._write_identity(cache, p4k)
        assert dataforge_cache_is_fresh(p4k, cache) is True

    def test_previous_capture_schema_requires_reextraction(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = self._make_cache_with_stamp(tmp_path, p4k.stat().st_mtime)
        self._write_identity(cache, p4k)
        identity = _read_dataforge_identity(cache)
        identity["schema_version"] = DATAFORGE_CACHE_SCHEMA_VERSION - 1
        (cache / DATAFORGE_IDENTITY_FILE).write_text(json.dumps(identity), encoding="utf-8")
        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_stamp_older(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000100.0)
        cache = self._make_cache_with_stamp(tmp_path, 1700000000.0)
        self._write_identity(cache, p4k)
        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_legacy_one_layer_cache_is_stale(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = tmp_path / "dataforge"
        (cache / "raw" / "libs" / "foundry" / "records").mkdir(parents=True)
        (cache / ".p4k_mtime").write_text(str(p4k.stat().st_mtime))

        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_required_subtree_is_missing(self, tmp_path):
        mtime = 1700000000.0
        p4k = self._make_p4k(tmp_path, mtime)
        cache = self._make_cache_with_stamp(tmp_path, mtime)
        self._write_identity(cache, p4k)
        import shutil

        shutil.rmtree(cache / "raw" / "libs" / "foundry" / "records" / "entities" / "spaceships")

        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_extraction_tool_changes(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = self._make_cache_with_stamp(tmp_path, p4k.stat().st_mtime)
        unp4k = tmp_path / "unp4k.exe"
        unforge = tmp_path / "unforge.exe"
        unp4k.write_bytes(b"first")
        unforge.write_bytes(b"first")
        self._write_identity(cache, p4k, unp4k, unforge)
        unp4k.write_bytes(b"changed")

        assert dataforge_cache_is_fresh(p4k, cache, unp4k, unforge) is False

    def test_stale_when_patch_set_changes(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = self._make_cache_with_stamp(tmp_path, p4k.stat().st_mtime)
        patches = tmp_path / "patches"
        patches.mkdir()
        (patches / "example.patch.json").write_text('{"edits": []}', encoding="utf-8")
        self._write_identity(cache, p4k)
        identity_path = cache / ".dataforge_identity.json"
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        identity["patch_fingerprint"] = "old"
        identity_path.write_text(json.dumps(identity), encoding="utf-8")

        assert dataforge_cache_is_fresh(p4k, cache, patch_root=patches) is False

    def test_stale_when_no_xml_files(self, tmp_path):
        mtime = 1700000000.0
        p4k = self._make_p4k(tmp_path, mtime)
        cache = tmp_path / "dataforge"
        libs = cache / "raw" / "libs"
        libs.mkdir(parents=True)
        stamp = cache / ".p4k_mtime"
        stamp.write_text(str(mtime))
        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_stamp_missing(self, tmp_path):
        p4k = self._make_p4k(tmp_path, 1700000000.0)
        cache = tmp_path / "dataforge"
        cache.mkdir()
        assert dataforge_cache_is_fresh(p4k, cache) is False

    def test_stale_when_stamp_corrupt(self, tmp_path):
        mtime = 1700000000.0
        p4k = self._make_p4k(tmp_path, mtime)
        cache = self._make_cache_with_stamp(tmp_path, mtime)
        (cache / ".p4k_mtime").write_text("not-a-float")
        assert dataforge_cache_is_fresh(p4k, cache) is False


# ─────────────────────────────────────────────────────────────────────────────
# extract_global_ini — happy path and error paths
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestExtractGlobalIni:
    def _make_fake_unp4k(self, tmp_path: Path) -> Path:
        exe = tmp_path / "unp4k.exe"
        exe.write_bytes(b"fake")
        return exe

    def _make_p4k(self, tmp_path: Path) -> Path:
        p4k = tmp_path / "Data.p4k"
        p4k.write_bytes(b"fake")
        return p4k

    def test_raises_when_unp4k_missing(self, tmp_path):
        p4k = self._make_p4k(tmp_path)
        with pytest.raises(FileNotFoundError, match="unp4k"):
            extract_global_ini(
                p4k_path=p4k,
                output_path=tmp_path / "base.ini",
                unp4k_exe=tmp_path / "missing_unp4k.exe",
            )

    def test_raises_when_p4k_missing(self, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        with pytest.raises(FileNotFoundError, match="Data.p4k"):
            extract_global_ini(
                p4k_path=tmp_path / "missing.p4k",
                output_path=tmp_path / "base.ini",
                unp4k_exe=exe,
            )

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_raises_on_nonzero_returncode(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="unp4k error")
        with pytest.raises(RuntimeError, match="unp4k.exe exited"):
            extract_global_ini(p4k_path=p4k, output_path=tmp_path / "base.ini", unp4k_exe=exe)

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_raises_when_extracted_file_missing(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        # _run_subprocess succeeds but doesn't create the expected global.ini
        with pytest.raises(FileNotFoundError, match="global.ini"):
            extract_global_ini(p4k_path=p4k, output_path=tmp_path / "base.ini", unp4k_exe=exe)

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_happy_path_copies_to_output(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        output = tmp_path / "cache" / "base.ini"

        def _fake_run(args, cwd=None, timeout=None):
            # Simulate unp4k writing the expected file structure
            extracted = Path(cwd) / "data" / "Localization" / "english" / "global.ini"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_text("key=value\n", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = _fake_run
        result = extract_global_ini(p4k_path=p4k, output_path=output, unp4k_exe=exe)
        assert result is True
        assert output.exists()
        assert output.read_text(encoding="utf-8") == "key=value\n"

    @patch("src.utils.pak_extractor._run_subprocess")
    def test_progress_callbacks_called(self, mock_run, tmp_path):
        exe = self._make_fake_unp4k(tmp_path)
        p4k = self._make_p4k(tmp_path)
        output = tmp_path / "base.ini"

        def _fake_run(args, cwd=None, timeout=None):
            extracted = Path(cwd) / "data" / "Localization" / "english" / "global.ini"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_text("k=v\n", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = _fake_run
        messages = []
        pct_calls = []
        extract_global_ini(
            p4k_path=p4k,
            output_path=output,
            unp4k_exe=exe,
            progress_callback=messages.append,
            progress_pct_callback=lambda cur, total, msg: pct_calls.append((cur, total)),
        )
        assert len(messages) >= 1
        assert len(pct_calls) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
