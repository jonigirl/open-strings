"""Manages the download and local caching of unp4k / unforge extraction tools."""

import hashlib
import logging
import shutil
import ssl
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

from src.utils.file_utils import atomic_write_bytes

logger = logging.getLogger(__name__)

TOOLS_VERSION = "v4.0.87-os1"
BUNDLED_UNFORGE_ASSET = f"unforge-openstrings-{TOOLS_VERSION}-win-x64.zip"
_UNP4K_VERSION = "v4.0.87"
_CUSTOM_TOOL_RELEASE = "v1.5.2"
_UNFORGE_SHA256 = "5c0674c725b92ed75f5babc0e77f5d7dfe6ed24a60ee6bf1b2b5bbe1ff703748"

_BASE_URL = f"https://github.com/dolkensp/unp4k/releases/download/{_UNP4K_VERSION}"
_UNP4K_ZIP_URL = f"{_BASE_URL}/unp4k-win-x64-{_UNP4K_VERSION}.zip"
_UNFORGE_ZIP_URL = f"https://github.com/jonigirl/open-strings/releases/download/{_CUSTOM_TOOL_RELEASE}/unforge-openstrings-{TOOLS_VERSION}-win-x64.zip"


def get_tools_dir() -> Path:
    """Return the versioned local cache directory for the tool binaries.

    Lives under ``%APPDATA%\\Open Strings\\tools\\<version>\\`` so it persists
    across app updates. A future version bump creates a fresh directory
    automatically without touching an older cached set.
    """
    import os

    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Open Strings" / "tools" / TOOLS_VERSION


def tools_are_present() -> bool:
    """Return True if both unp4k.exe and unforge.cli.exe exist in the tools directory."""
    d = get_tools_dir()
    return (d / "unp4k.exe").exists() and (d / "unforge.cli.exe").exists()


def get_bundled_unforge_package() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    package = Path(sys.executable).resolve().parent / "tools" / BUNDLED_UNFORGE_ASSET
    return package if package.is_file() else None


def download_tools(
    progress_callback=None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Download and extract unp4k and unforge into the tools directory.

    Downloads upstream unp4k and the digest-pinned patched unforge package,
    extracts them (preserving directory structure) into :func:`get_tools_dir`.

    Args:
        progress_callback: Optional ``callable(str)`` called with a
            human-readable status message during download and extraction.
        cancel_event: Optional :class:`threading.Event`. When set, the
            download is aborted and a ``RuntimeError`` is raised.

    Raises:
        RuntimeError: If the download is cancelled via *cancel_event*.
        urllib.error.URLError: On network errors.
        zipfile.BadZipFile: If a downloaded file is corrupt.
    """
    tools_dir = get_tools_dir()
    tools_dir.mkdir(parents=True, exist_ok=True)

    _CHUNK = 65536

    # (label, zip_url, actual_exe_name) — unforge ships as unforge.cli.exe, not unforge.exe
    for name, url, exe_name in [
        ("unp4k", _UNP4K_ZIP_URL, "unp4k.exe"),
        ("unforge", _UNFORGE_ZIP_URL, "unforge.cli.exe"),
    ]:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Download cancelled")

        if (tools_dir / exe_name).is_file():
            _report(progress_callback, f"Using cached {name}")
            continue

        bundled = get_bundled_unforge_package() if name == "unforge" else None
        if bundled is not None:
            with bundled.open("rb") as archive:
                digest = hashlib.file_digest(archive, "sha256").hexdigest()
            if digest != _UNFORGE_SHA256:
                raise RuntimeError("Bundled patched unforge package SHA-256 mismatch; refusing extraction")
            _report(progress_callback, "Installing bundled unforge…")
            with zipfile.ZipFile(bundled) as archive:
                if "unforge.cli.exe" not in archive.namelist():
                    raise FileNotFoundError("Bundled package is missing unforge.cli.exe")
                _install_tool_archive(archive, tools_dir, exe_name, cancel_event)
            continue

        _report(progress_callback, f"Downloading {name}…")
        logger.info(f"Downloading {name} from {url}")

        if not url.startswith("https://"):
            raise ValueError(f"Only HTTPS URLs are accepted for downloads; got: {url!r}")

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                tmp_path = Path(tmp_file.name)
                with urllib.request.urlopen(url, timeout=60, context=ssl.create_default_context()) as response:
                    total = int(response.headers.get("Content-Length") or 0)
                    downloaded = 0
                    while True:
                        if cancel_event and cancel_event.is_set():
                            raise RuntimeError("Download cancelled")
                        chunk = response.read(_CHUNK)
                        if not chunk:
                            break
                        tmp_file.write(chunk)
                        downloaded += len(chunk)
                        mb_done = downloaded // (1024 * 1024)
                        if total:
                            mb_total = total // (1024 * 1024)
                            _report(
                                progress_callback,
                                f"Downloading {name}… {mb_done} / {mb_total} MB",
                            )
                        else:
                            _report(progress_callback, f"Downloading {name}… {mb_done} MB")

            if name == "unforge":
                with tmp_path.open("rb") as archive:
                    digest = hashlib.file_digest(archive, "sha256").hexdigest()
                if digest != _UNFORGE_SHA256:
                    raise RuntimeError("Patched unforge package SHA-256 mismatch; refusing extraction")

            _report(progress_callback, f"Extracting {name}…")
            logger.info(f"Extracting {name} to {tools_dir}")
            with zipfile.ZipFile(tmp_path) as zf:
                _install_tool_archive(zf, tools_dir, exe_name, cancel_event)

            logger.info(f"{exe_name} extracted OK")

        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


def _install_tool_archive(
    archive: zipfile.ZipFile, tools_dir: Path, exe_name: str, cancel_event: threading.Event | None
) -> None:
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("Download cancelled")
    with tempfile.TemporaryDirectory(prefix="openstrings-tool-") as directory:
        staging = Path(directory)
        _safe_extractall(archive, staging, cancel_event)
        executable = staging / exe_name
        if not executable.is_file():
            nested = next(staging.rglob(exe_name), None)
            if nested is None or not nested.is_file():
                raise FileNotFoundError(f"{exe_name} not found in extraction package")
            nested.replace(executable)
        for source in staging.rglob("*"):
            if source.is_file() and source != executable:
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("Download cancelled")
                target = tools_dir / source.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Download cancelled")
        atomic_write_bytes(tools_dir / exe_name, executable.read_bytes())


def _safe_extractall(zf: zipfile.ZipFile, dest: Path, cancel_event: threading.Event | None = None) -> None:
    """Extract *zf* into *dest*, rejecting any path-traversal entries.

    ``zipfile.ZipFile.extractall`` does not sanitise entry names, so a zip
    containing ``../../evil.exe`` would write outside *dest*.  We resolve
    each entry's target and refuse to extract anything that escapes the
    destination directory (CWE-22 / zip slip).
    """
    dest_resolved = dest.resolve()
    for entry in zf.infolist():
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Download cancelled")
        target = (dest / entry.filename).resolve()
        if dest_resolved != target and dest_resolved not in target.parents:
            raise ValueError(f"Unsafe zip entry rejected (path traversal): {entry.filename!r}")
        zf.extract(entry, dest)


def _report(callback, message: str) -> None:
    if callback is not None:
        callback(message)
