"""Tests for tools_manager — download, presence check, and directory resolution."""

import hashlib
import io
import zipfile
from unittest.mock import patch

import pytest
from src.utils.tools_manager import (
    TOOLS_VERSION,
    download_tools,
    get_tools_dir,
    tools_are_present,
)


@pytest.mark.unit
class TestGetToolsDir:
    def test_contains_app_name(self):
        d = get_tools_dir()
        assert "Open Strings" in str(d)

    def test_contains_version(self):
        d = get_tools_dir()
        assert TOOLS_VERSION in str(d)

    def test_uses_appdata_env(self, tmp_path):
        with patch.dict("os.environ", {"APPDATA": str(tmp_path)}):
            d = get_tools_dir()
        assert str(tmp_path) in str(d)

    def test_falls_back_when_appdata_missing(self):
        env = {"APPDATA": ""}
        with patch.dict("os.environ", env):
            import os

            os.environ.pop("APPDATA", None)
            d = get_tools_dir()
        assert "Open Strings" in str(d)


@pytest.mark.unit
class TestToolsArePresent:
    def test_false_when_directory_empty(self, tmp_path):
        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            assert not tools_are_present()

    def test_false_when_only_unp4k_exists(self, tmp_path):
        (tmp_path / "unp4k.exe").write_text("x")
        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            assert not tools_are_present()

    def test_false_when_only_unforge_exists(self, tmp_path):
        (tmp_path / "unforge.cli.exe").write_text("x")
        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            assert not tools_are_present()

    def test_true_when_both_exes_exist(self, tmp_path):
        (tmp_path / "unp4k.exe").write_text("x")
        (tmp_path / "unforge.cli.exe").write_text("x")
        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            assert tools_are_present()


def _make_zip(*entries: tuple[str, str]) -> bytes:
    """Build an in-memory zip with the given (name, content) entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries:
            zf.writestr(name, content)
    return buf.getvalue()


class _FakeResponse:
    """Minimal urllib response stand-in."""

    def __init__(self, data: bytes) -> None:
        self._stream = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n: int) -> bytes:
        return self._stream.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@pytest.mark.unit
class TestDownloadTools:
    def test_failed_bundle_extraction_does_not_publish_executable_and_retry_recovers(self, tmp_path, monkeypatch):
        from src.utils import tools_manager as tools

        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "unp4k.exe").write_text("existing", encoding="utf-8")
        package = tmp_path / tools.BUNDLED_UNFORGE_ASSET
        payload = _make_zip(("unforge.cli.exe", "complete"))
        package.write_bytes(payload)
        monkeypatch.setattr(tools, "get_tools_dir", lambda: cache)
        monkeypatch.setattr(tools, "get_bundled_unforge_package", lambda: package)
        monkeypatch.setattr(tools, "_UNFORGE_SHA256", hashlib.sha256(payload).hexdigest())

        def fail_extract(archive, staging, cancel_event=None):
            (staging / "unforge.cli.exe").write_text("truncated", encoding="utf-8")
            raise OSError("write failed")

        with patch.object(tools, "_safe_extractall", side_effect=fail_extract):
            with pytest.raises(OSError, match="write failed"):
                download_tools()
        assert not (cache / "unforge.cli.exe").exists()
        assert not tools_are_present()
        with patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected download")):
            download_tools()
        assert (cache / "unforge.cli.exe").read_text() == "complete"
        assert tools_are_present()

    def test_cancel_bundled_install_does_not_publish_executable(self, tmp_path, monkeypatch):
        import threading

        from src.utils import tools_manager as tools

        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "unp4k.exe").write_text("existing", encoding="utf-8")
        package = tmp_path / tools.BUNDLED_UNFORGE_ASSET
        payload = _make_zip(("unforge.cli.exe", "complete"))
        package.write_bytes(payload)
        cancel = threading.Event()
        monkeypatch.setattr(tools, "get_tools_dir", lambda: cache)
        monkeypatch.setattr(tools, "get_bundled_unforge_package", lambda: package)
        monkeypatch.setattr(tools, "_UNFORGE_SHA256", hashlib.sha256(payload).hexdigest())

        def progress(message):
            if message.startswith("Installing bundled"):
                cancel.set()

        with pytest.raises(RuntimeError, match="cancelled"):
            download_tools(progress_callback=progress, cancel_event=cancel)
        assert not (cache / "unforge.cli.exe").exists()

    def test_bundled_package_recovers_missing_unforge_without_network(self, tmp_path, monkeypatch):
        from src.utils import tools_manager as tools

        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "unp4k.exe").write_text("existing", encoding="utf-8")
        package = tmp_path / tools.BUNDLED_UNFORGE_ASSET
        payload = _make_zip(("unforge.cli.exe", "patched"), ("LICENSE.txt", "license"))
        package.write_bytes(payload)
        monkeypatch.setattr(tools, "get_tools_dir", lambda: cache)
        monkeypatch.setattr(tools, "get_bundled_unforge_package", lambda: package)
        monkeypatch.setattr(tools, "_UNFORGE_SHA256", hashlib.sha256(payload).hexdigest())
        with patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected download")):
            download_tools()
        assert (cache / "unp4k.exe").read_text() == "existing"
        assert (cache / "unforge.cli.exe").read_text() == "patched"
        assert tools_are_present()

    def test_bundled_package_supports_fresh_cache(self, tmp_path, monkeypatch):
        from src.utils import tools_manager as tools

        package = tmp_path / tools.BUNDLED_UNFORGE_ASSET
        payload = _make_zip(("unforge.cli.exe", "patched"))
        package.write_bytes(payload)
        monkeypatch.setattr(tools, "get_tools_dir", lambda: tmp_path / "cache")
        monkeypatch.setattr(tools, "get_bundled_unforge_package", lambda: package)
        monkeypatch.setattr(tools, "_UNFORGE_SHA256", hashlib.sha256(payload).hexdigest())
        with patch(
            "urllib.request.urlopen", return_value=_FakeResponse(_make_zip(("unp4k.exe", "official")))
        ) as download:
            download_tools()
        download.assert_called_once()
        assert download.call_args.args[0] == tools._UNP4K_ZIP_URL
        assert tools_are_present()

    def test_corrupt_bundle_does_not_fall_back_to_unpublished_url(self, tmp_path, monkeypatch):
        from src.utils import tools_manager as tools

        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "unp4k.exe").write_text("existing", encoding="utf-8")
        package = tmp_path / tools.BUNDLED_UNFORGE_ASSET
        package.write_bytes(_make_zip(("unforge.cli.exe", "wrong")))
        monkeypatch.setattr(tools, "get_tools_dir", lambda: cache)
        monkeypatch.setattr(tools, "get_bundled_unforge_package", lambda: package)
        monkeypatch.setattr(tools, "_UNFORGE_SHA256", "0" * 64)
        with patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected download")):
            with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
                download_tools()
        assert not (cache / "unforge.cli.exe").exists()

    def test_frozen_bundle_resolves_beside_executable_not_temporary_meipass(self, tmp_path, monkeypatch):
        from src.utils import tools_manager as tools

        package = tmp_path / "tools" / tools.BUNDLED_UNFORGE_ASSET
        package.parent.mkdir()
        package.write_bytes(b"example")
        monkeypatch.setattr(tools.sys, "frozen", True, raising=False)
        monkeypatch.setattr(tools.sys, "executable", str(tmp_path / "OpenStrings.exe"))
        monkeypatch.setattr(tools.sys, "_MEIPASS", str(tmp_path / "temporary"), raising=False)
        assert tools.get_bundled_unforge_package() == package

    def _patch_urlopen(self, responses: list[bytes]):
        """Return a context-manager patch that serves responses in order."""
        call_iter = iter(responses)

        def fake_urlopen(url, **kwargs):
            return _FakeResponse(next(call_iter))

        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(patch("urllib.request.urlopen", side_effect=fake_urlopen))
        if len(responses) > 1:
            stack.enter_context(
                patch("src.utils.tools_manager._UNFORGE_SHA256", hashlib.sha256(responses[1]).hexdigest())
            )
        return stack

    def test_extracts_unp4k_and_unforge_exes(self, tmp_path):
        unp4k_zip = _make_zip(("unp4k.exe", "bin"), ("x64/libzstd.dll", "dll"))
        unforge_zip = _make_zip(("unforge.cli.exe", "bin"), ("Zstd.Net.dll", "dll"))

        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            with self._patch_urlopen([unp4k_zip, unforge_zip]):
                download_tools()

        assert (tmp_path / "unp4k.exe").exists()
        assert (tmp_path / "unforge.cli.exe").exists()

    def test_supporting_files_also_extracted(self, tmp_path):
        unp4k_zip = _make_zip(("unp4k.exe", "b"), ("x64/libzstd.dll", "d"), ("x86/libzstd.dll", "d"))
        unforge_zip = _make_zip(
            ("unforge.cli.exe", "b"),
            ("ICSharpCode.SharpZipLib.dll", "d"),
            ("Zstd.Net.dll", "d"),
        )

        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            with self._patch_urlopen([unp4k_zip, unforge_zip]):
                download_tools()

        assert (tmp_path / "x64" / "libzstd.dll").exists()
        assert (tmp_path / "Zstd.Net.dll").exists()

    def test_progress_callback_called(self, tmp_path):
        unp4k_zip = _make_zip(("unp4k.exe", "b"))
        unforge_zip = _make_zip(("unforge.cli.exe", "b"))
        messages = []

        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            with self._patch_urlopen([unp4k_zip, unforge_zip]):
                download_tools(progress_callback=messages.append)

        assert any("unp4k" in m for m in messages)
        assert any("unforge" in m for m in messages)

    def test_cancel_event_aborts_before_second_download(self, tmp_path):
        import threading

        unp4k_zip = _make_zip(("unp4k.exe", "b"))
        cancel = threading.Event()

        call_count = 0

        def fake_urlopen(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                cancel.set()  # cancel after first zip starts
            return _FakeResponse(unp4k_zip)

        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with pytest.raises(RuntimeError, match="cancelled"):
                    download_tools(cancel_event=cancel)

        # Should not have attempted the second download
        assert call_count == 1

    def test_exe_in_subdirectory_promoted_to_flat_path(self, tmp_path):
        # Reproduces a zip layout where the exe is nested inside a subdirectory
        # rather than placed at the archive root.
        unp4k_zip = _make_zip(("unp4k.exe", "bin"))
        unforge_zip = _make_zip(("unforge-win-x64-v4.0.83/unforge.cli.exe", "bin"))

        with patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path):
            with self._patch_urlopen([unp4k_zip, unforge_zip]):
                download_tools()

        # Both exes must be at the flat expected location after promotion
        assert (tmp_path / "unp4k.exe").exists()
        assert (tmp_path / "unforge.cli.exe").exists()

    def test_tools_dir_created_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        unp4k_zip = _make_zip(("unp4k.exe", "b"))
        unforge_zip = _make_zip(("unforge.cli.exe", "b"))

        with patch("src.utils.tools_manager.get_tools_dir", return_value=nested):
            with self._patch_urlopen([unp4k_zip, unforge_zip]):
                download_tools()

        assert nested.is_dir()

    def test_corrupt_custom_package_rejected_before_extraction(self, tmp_path):
        unp4k_zip = _make_zip(("unp4k.exe", "b"))
        unforge_zip = _make_zip(("unforge.cli.exe", "corrupt"))
        with (
            patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path),
            self._patch_urlopen([unp4k_zip, unforge_zip]),
            patch("src.utils.tools_manager._UNFORGE_SHA256", "0" * 64),
        ):
            with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
                download_tools()
        assert not (tmp_path / "unforge.cli.exe").exists()


@pytest.mark.unit
class TestSafeExtractall:
    def test_normal_entries_extracted(self, tmp_path):
        from src.utils import tools_manager as _tm

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("unp4k.exe", "bin")
            zf.writestr("x64/libzstd.dll", "dll")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            _tm._safe_extractall(zf, tmp_path)
        assert (tmp_path / "unp4k.exe").exists()
        assert (tmp_path / "x64" / "libzstd.dll").exists()

    def test_path_traversal_entry_rejected(self, tmp_path):
        from src.utils import tools_manager as _tm

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../evil.exe", "bad")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            with pytest.raises(ValueError, match="path traversal"):
                _tm._safe_extractall(zf, tmp_path)

    def test_absolute_path_entry_rejected(self, tmp_path):
        from src.utils import tools_manager as _tm

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("/etc/passwd", "bad")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            with pytest.raises(ValueError, match="path traversal"):
                _tm._safe_extractall(zf, tmp_path)


def test_download_error_does_not_blame_network_or_recommend_stock_unforge():
    from src.gui.tool_download_dialog import ToolDownloadDialog
    from src.utils.tools_manager import _UNFORGE_ZIP_URL

    with patch("src.gui.tool_download_dialog.QMessageBox.warning") as warning:
        ToolDownloadDialog._on_error(None, "HTTP Error 404: Not Found")
    text = warning.call_args.args[2]
    assert "release asset is unavailable" in text
    assert "not a compatible replacement" in text
    assert _UNFORGE_ZIP_URL in text
    assert "This is usually caused by" not in text
