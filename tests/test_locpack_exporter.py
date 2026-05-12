"""Tests for src.utils.locpack_exporter — zip packaging of applied global.ini."""

from __future__ import annotations

import zipfile
from datetime import datetime

import pytest
from src.utils.locpack_exporter import default_locpack_filename, write_locpack_zip

pytestmark = pytest.mark.unit


# ── default_locpack_filename ──────────────────────────────────────────────────
class TestDefaultLocpackFilename:
    def test_uses_channel_and_date(self):
        result = default_locpack_filename("LIVE", today=datetime(2026, 5, 12))
        assert result == "OpenStrings-LocPack-LIVE-20260512.zip"

    def test_distinct_per_channel(self):
        """Channel-specific because LIVE/PTU stock keys diverge — applying
        a PTU export to LIVE could produce missing-key validation errors.
        Filename surfaces the channel so recipients don't mix them up."""
        live = default_locpack_filename("LIVE", today=datetime(2026, 5, 12))
        ptu = default_locpack_filename("PTU", today=datetime(2026, 5, 12))
        assert live != ptu
        assert "LIVE" in live
        assert "PTU" in ptu

    def test_has_zip_suffix(self):
        result = default_locpack_filename("EPTU", today=datetime(2026, 5, 12))
        assert result.endswith(".zip")

    def test_today_default_does_not_raise(self):
        result = default_locpack_filename("LIVE")
        assert result.startswith("OpenStrings-LocPack-LIVE-")
        assert result.endswith(".zip")

    def test_date_format_is_yyyymmdd(self):
        result = default_locpack_filename("HOTFIX", today=datetime(2026, 1, 5))
        assert "20260105" in result


# ── write_locpack_zip ─────────────────────────────────────────────────────────
class TestWriteLocpackZip:
    def test_writes_global_ini_at_zip_root(self, tmp_path):
        """Zip should contain global.ini at the root, no nested dirs —
        recipients drop straight into the game's loc directory."""
        src = tmp_path / "global.ini"
        payload = b"vehicle_NameTestShip=Test Ship\nvehicle_NameTestCar=Test Car\n"
        src.write_bytes(payload)
        dest = tmp_path / "out.zip"

        write_locpack_zip(src, dest)

        with zipfile.ZipFile(dest) as zf:
            names = zf.namelist()
        assert names == ["global.ini"]

    def test_returns_source_size(self, tmp_path):
        src = tmp_path / "global.ini"
        payload = b"key=value\n" * 100
        src.write_bytes(payload)
        dest = tmp_path / "out.zip"

        result = write_locpack_zip(src, dest)

        assert result == len(payload)

    def test_overwrite_existing(self, tmp_path):
        src = tmp_path / "global.ini"
        src.write_bytes(b"first=value\n")
        dest = tmp_path / "out.zip"
        dest.write_bytes(b"stale data")

        write_locpack_zip(src, dest)

        with zipfile.ZipFile(dest) as zf:
            assert zf.read("global.ini") == b"first=value\n"

    def test_uses_deflate_compression(self, tmp_path):
        src = tmp_path / "global.ini"
        # Highly compressible payload to distinguish DEFLATE from STORED
        src.write_bytes(b"key=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n" * 500)
        dest = tmp_path / "out.zip"

        write_locpack_zip(src, dest)

        with zipfile.ZipFile(dest) as zf:
            info = zf.getinfo("global.ini")
        assert info.compress_type == zipfile.ZIP_DEFLATED

    def test_raises_if_source_missing(self, tmp_path):
        src = tmp_path / "does_not_exist.ini"
        dest = tmp_path / "out.zip"

        with pytest.raises(FileNotFoundError, match="Applied global.ini not found"):
            write_locpack_zip(src, dest)
