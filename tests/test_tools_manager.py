"""Tests for tools_manager — download, presence check, and directory resolution."""

import hashlib
import io
import threading
import time
import zipfile
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

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


@pytest.fixture
def missing_unforge(tmp_path, monkeypatch):
    from src.utils import tools_manager as tools

    (tmp_path / "unp4k.exe").write_text("cached", encoding="utf-8")
    payload = _make_zip(("unforge.cli.exe", "patched"))
    monkeypatch.setattr(tools, "get_tools_dir", lambda: tmp_path)
    monkeypatch.setattr(tools, "get_bundled_unforge_package", lambda: None)
    monkeypatch.setattr(tools, "_UNFORGE_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(tools.tempfile, "tempdir", str(tmp_path))
    return payload


@pytest.mark.unit
class TestDownloadRecovery:
    @pytest.mark.parametrize("code", [500, 502, 503, 504])
    def test_gateway_error_recovers_via_official_asset_api(self, tmp_path, missing_unforge, code, caplog):
        from src.utils import tools_manager as tools

        messages = []
        error = HTTPError(tools._UNFORGE_ZIP_URL, code, "Server error", None, None)
        with patch("urllib.request.urlopen", side_effect=[error, _FakeResponse(missing_unforge)]) as request:
            download_tools(progress_callback=messages.append)

        assert request.call_args_list[0].args[0] == tools._UNFORGE_ZIP_URL
        fallback = request.call_args_list[1].args[0]
        assert isinstance(fallback, Request)
        assert fallback.full_url == "https://api.github.com/repos/jonigirl/open-strings/releases/assets/623494613"
        assert fallback.get_header("Accept") == "application/octet-stream"
        assert (tmp_path / "unforge.cli.exe").read_text() == "patched"
        assert any("Retrying unforge" in message for message in messages)
        assert str(code) in caplog.text
        assert not list(tmp_path.glob("*.zip"))

    def test_unp4k_also_recovers_via_its_pinned_asset_api(self, tmp_path, missing_unforge, monkeypatch):
        from src.utils import tools_manager as tools

        (tmp_path / "unp4k.exe").unlink()
        (tmp_path / "unforge.cli.exe").write_text("cached", encoding="utf-8")
        payload = _make_zip(("unp4k.exe", "official"))
        monkeypatch.setattr(tools, "_UNP4K_SHA256", hashlib.sha256(payload).hexdigest())
        error = HTTPError(tools._UNP4K_ZIP_URL, 504, "Gateway Time-out", None, None)
        with patch("urllib.request.urlopen", side_effect=[error, _FakeResponse(payload)]) as request:
            download_tools()

        fallback = request.call_args_list[1].args[0]
        assert isinstance(fallback, Request)
        assert fallback.full_url == "https://api.github.com/repos/dolkensp/unp4k/releases/assets/427794604"
        assert fallback.get_header("Accept") == "application/octet-stream"
        assert (tmp_path / "unp4k.exe").read_text() == "official"

    @pytest.mark.parametrize("code", [403, 404])
    def test_permanent_http_error_is_not_retried(self, tmp_path, missing_unforge, code):
        from src.utils import tools_manager as tools

        error = HTTPError(tools._UNFORGE_ZIP_URL, code, "Unavailable", None, None)
        with patch("urllib.request.urlopen", side_effect=error) as request:
            with pytest.raises(HTTPError) as caught:
                download_tools()
        assert caught.value is error
        assert request.call_count == 1
        assert not (tmp_path / "unforge.cli.exe").exists()
        assert not list(tmp_path.glob("*.zip"))

    def test_retries_are_bounded_and_final_error_is_preserved(self, tmp_path, missing_unforge):
        from src.utils import tools_manager as tools

        errors = [
            HTTPError(tools._UNFORGE_ZIP_URL, 504, f"Gateway timeout {attempt}", None, None) for attempt in range(3)
        ]
        with patch("urllib.request.urlopen", side_effect=errors) as request:
            with pytest.raises(HTTPError) as caught:
                download_tools()
        assert caught.value is errors[-1]
        assert request.call_count == 3
        assert not (tmp_path / "unforge.cli.exe").exists()
        assert not list(tmp_path.glob("*.zip"))

    @pytest.mark.parametrize(
        "error",
        [
            TimeoutError("Read timed out"),
            ConnectionResetError("Connection reset"),
            URLError("Connection lost"),
            IncompleteRead(b"partial", 100),
        ],
    )
    def test_interrupted_download_restarts_without_partial_bytes(self, tmp_path, missing_unforge, error):
        response = _FakeResponse(missing_unforge)
        with (
            patch.object(response, "read", side_effect=[missing_unforge[:16], error]),
            patch("urllib.request.urlopen", side_effect=[response, _FakeResponse(missing_unforge)]) as request,
        ):
            download_tools()
        assert request.call_count == 2
        assert (tmp_path / "unforge.cli.exe").read_text() == "patched"
        assert not list(tmp_path.glob("*.zip"))

    def test_truncated_response_is_retried_before_hash_validation(self, tmp_path, missing_unforge):
        response = _FakeResponse(missing_unforge[:16])
        response.headers["Content-Length"] = str(len(missing_unforge))
        with patch("urllib.request.urlopen", side_effect=[response, _FakeResponse(missing_unforge)]) as request:
            download_tools()
        assert request.call_count == 2
        assert (tmp_path / "unforge.cli.exe").read_text() == "patched"

    def test_cancel_during_retry_prevents_next_request(self, tmp_path, missing_unforge):
        from src.utils import tools_manager as tools

        cancel = threading.Event()

        def progress(message):
            if message.startswith("Retrying"):
                cancel.set()

        error = HTTPError(tools._UNFORGE_ZIP_URL, 504, "Gateway Time-out", None, None)
        with patch("urllib.request.urlopen", side_effect=error) as request:
            with pytest.raises(RuntimeError, match="Download cancelled"):
                download_tools(progress_callback=progress, cancel_event=cancel)
        assert request.call_count == 1
        assert not (tmp_path / "unforge.cli.exe").exists()
        assert not list(tmp_path.glob("*.zip"))

    def test_api_fallback_still_rejects_wrong_digest(self, tmp_path, missing_unforge):
        from src.utils import tools_manager as tools

        error = HTTPError(tools._UNFORGE_ZIP_URL, 504, "Gateway Time-out", None, None)
        corrupt = _make_zip(("unforge.cli.exe", "wrong"))
        with patch("urllib.request.urlopen", side_effect=[error, _FakeResponse(corrupt)]) as request:
            with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
                download_tools()
        assert request.call_count == 2
        assert not (tmp_path / "unforge.cli.exe").exists()
        assert not list(tmp_path.glob("*.zip"))


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
        unp4k_zip = _make_zip(("unp4k.exe", "official"))
        monkeypatch.setattr(tools, "_UNP4K_SHA256", hashlib.sha256(unp4k_zip).hexdigest())
        with patch("urllib.request.urlopen", return_value=_FakeResponse(unp4k_zip)) as download:
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
        stack.enter_context(patch("src.utils.tools_manager._UNP4K_SHA256", hashlib.sha256(responses[0]).hexdigest()))
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

    def test_corrupt_unp4k_package_rejected_before_extraction(self, tmp_path):
        unp4k_zip = _make_zip(("unp4k.exe", "tampered"))
        with (
            patch("src.utils.tools_manager.get_tools_dir", return_value=tmp_path),
            self._patch_urlopen([unp4k_zip]),
            patch("src.utils.tools_manager._UNP4K_SHA256", "0" * 64),
        ):
            with pytest.raises(RuntimeError, match="unp4k package SHA-256 mismatch"):
                download_tools()
        assert not (tmp_path / "unp4k.exe").exists()


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
