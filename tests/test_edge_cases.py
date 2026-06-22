from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from src.utils import enhancement_formatters

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "generate_enhancements_ini.py"


@pytest.fixture(scope="module")
def gen_module():
    spec = importlib.util.spec_from_file_location("generate_enhancements_edge_test", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _xml(s: str) -> ET.Element:
    return ET.fromstring(s)


# ── Empty/Missing File Handling ──────────────────────────────────────────────


def test_parse_ini_empty_file(gen_module, tmp_path):
    """Empty file returns empty dict."""
    empty_file = tmp_path / "empty.ini"
    empty_file.write_text("", encoding="utf-8")
    result = gen_module.parse_ini(empty_file)
    assert result == {}


def test_parse_ini_only_comments(gen_module, tmp_path):
    """File with only comments returns empty dict."""
    comments_file = tmp_path / "comments.ini"
    comments_file.write_text("; This is a comment\n; Another comment\n  ; Indented comment\n", encoding="utf-8")
    result = gen_module.parse_ini(comments_file)
    assert result == {}


def test_parse_ini_only_whitespace(gen_module, tmp_path):
    """File with only whitespace returns empty dict."""
    ws_file = tmp_path / "whitespace.ini"
    ws_file.write_text("   \n\t\n  \n", encoding="utf-8")
    result = gen_module.parse_ini(ws_file)
    assert result == {}


def test_parse_ini_missing_file(gen_module, tmp_path):
    """Missing file raises FileNotFoundError."""
    missing_file = tmp_path / "nonexistent.ini"
    with pytest.raises(FileNotFoundError):
        gen_module.parse_ini(missing_file)


def test_parse_ini_malformed_lines_skipped(gen_module, tmp_path):
    """Lines without '=' are skipped gracefully."""
    malformed_file = tmp_path / "malformed.ini"
    malformed_file.write_text(
        "valid_key=valid_value\nthis line has no equals sign\nanother_key=another_value\nno equals here either\n",
        encoding="utf-8",
    )
    result = gen_module.parse_ini(malformed_file)
    assert result == {"valid_key": "valid_value", "another_key": "another_value"}


# ── Shield Formatter Edge Cases ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_xml",
    [
        "<Entity></Entity>",  # Empty
        "<Entity><Shield/></Entity>",  # No attributes
        "<Entity><Shield MaxHealth='bad'/></Entity>",  # Non-numeric
        "<Entity><Shield MaxHealth='-100'/></Entity>",  # Negative
        "<Entity><Shield MaxHealth='NaN'/></Entity>",  # NaN string
        "<Entity><Shield MaxHealth='0'/></Entity>",  # Zero
    ],
)
def test_shield_formatter_handles_malformed_data(bad_xml):
    """Shield formatter degrades gracefully with malformed XML."""
    root = _xml(bad_xml)
    result = enhancement_formatters.enhancements_shield(root)
    assert isinstance(result, str)
    # Should either return empty string or contain placeholder/fallback markers
    # Must not crash or raise exceptions


@pytest.mark.parametrize(
    "bad_xml",
    [
        "<Entity></Entity>",  # Empty
        "<Entity><Cooler/></Entity>",  # No attributes
        "<Entity><Cooler CoolingRate='invalid'/></Entity>",  # Non-numeric
    ],
)
def test_cooler_formatter_handles_malformed_data(bad_xml):
    """Cooler formatter degrades gracefully with malformed XML."""
    root = _xml(bad_xml)
    result = enhancement_formatters.enhancements_cooler(root)
    assert isinstance(result, str)


@pytest.mark.parametrize(
    "bad_xml",
    [
        "<Entity></Entity>",  # Empty
        "<Entity><PowerPlant/></Entity>",  # No attributes
        "<Entity><PowerPlant PowerDraw='bad'/></Entity>",  # Non-numeric
    ],
)
def test_powerplant_formatter_handles_malformed_data(bad_xml):
    """PowerPlant formatter degrades gracefully with malformed XML."""
    root = _xml(bad_xml)
    result = enhancement_formatters.enhancements_powerplant(root)
    assert isinstance(result, str)


@pytest.mark.parametrize(
    "bad_xml",
    [
        "<Entity></Entity>",  # Empty
        "<Entity><QuantumDrive/></Entity>",  # No attributes
        "<Entity><QuantumDrive FuelRate='invalid'/></Entity>",  # Non-numeric
    ],
)
def test_quantum_drive_formatter_handles_malformed_data(bad_xml):
    """QuantumDrive formatter degrades gracefully with malformed XML."""
    root = _xml(bad_xml)
    result = enhancement_formatters.enhancements_quantum_drive(root)
    assert isinstance(result, str)


@pytest.mark.parametrize(
    "bad_xml",
    [
        "<Entity></Entity>",  # Empty
        "<Entity><Radar/></Entity>",  # No attributes
        "<Entity><Radar RangeMax='bad'/></Entity>",  # Non-numeric
    ],
)
def test_radar_formatter_handles_malformed_data(bad_xml):
    """Radar formatter degrades gracefully with malformed XML."""
    root = _xml(bad_xml)
    result = enhancement_formatters.enhancements_radar(root)
    assert isinstance(result, str)


@pytest.mark.parametrize(
    "bad_xml",
    [
        "<Entity></Entity>",  # Empty
        "<Entity><Missile/></Entity>",  # No attributes
        "<Entity><Missile DamageTotal='invalid'/></Entity>",  # Non-numeric
    ],
)
def test_missile_formatter_handles_malformed_data(bad_xml):
    """Missile formatter degrades gracefully with malformed XML."""
    root = _xml(bad_xml)
    result = enhancement_formatters.enhancements_missile(root)
    assert isinstance(result, str)


# ── Weapon Formatter Edge Cases ──────────────────────────────────────────────


def test_weapon_formatter_empty_entity():
    """Weapon formatter handles empty entity."""
    root = _xml("<Entity></Entity>")
    result = enhancement_formatters.enhancements_weapon(root, {}, None)
    assert isinstance(result, str)


def test_weapon_formatter_missing_fire_rate_hook():
    """Weapon formatter handles missing fire rate hook gracefully."""
    root = _xml("<Entity><Weapon/></Entity>")
    result = enhancement_formatters.enhancements_weapon(root, {}, None)
    assert isinstance(result, str)


# ── Mission Formatter Edge Cases ─────────────────────────────────────────────


def test_mission_formatter_empty_entity():
    """Mission formatter handles empty entity."""
    root = _xml("<Entity></Entity>")
    result = enhancement_formatters.enhancements_mission(root, {})
    assert isinstance(result, str)


def test_mission_formatter_empty_reputation_lookup():
    """Mission formatter handles empty reputation lookup."""
    root = _xml("<Entity><Mission/></Entity>")
    result = enhancement_formatters.enhancements_mission(root, {})
    assert isinstance(result, str)


# ── FPS Attachment Formatter Edge Cases ──────────────────────────────────────


def test_fps_attachment_formatter_empty_entity():
    """FPS attachment formatter handles empty entity."""
    root = _xml("<Entity></Entity>")
    result = enhancement_formatters.enhancements_fps_attachment(root)
    assert isinstance(result, str)


# ── Hook Injection Tests ──────────────────────────────────────────────────────


def test_shield_formatter_works_with_minimal_data():
    """Shield formatter handles minimal data gracefully (may produce empty output)."""
    root = _xml("<Entity><Shield MaxHealth='1000'/></Entity>")
    result = enhancement_formatters.enhancements_shield(root)
    assert isinstance(result, str)
    # Empty output is acceptable for minimal data


def test_mission_formatter_with_none_hooks():
    """Mission formatter doesn't crash when hooks return None."""
    # This tests the default hook behavior
    root = _xml("<Entity><Mission/></Entity>")
    result = enhancement_formatters.enhancements_mission(root, {})
    assert isinstance(result, str)


def test_weapon_formatter_with_none_fire_rate():
    """Weapon formatter handles None fire_rate gracefully."""
    root = _xml("<Entity><Weapon/></Entity>")
    # fire_rate hook returns None by default
    result = enhancement_formatters.enhancements_weapon(root, {}, None)
    assert isinstance(result, str)


# ── Formatter Return Type Validation ──────────────────────────────────────────


def test_all_formatters_return_strings():
    """All formatters must return strings, never None or other types."""
    root = _xml("<Entity></Entity>")

    formatters = [
        lambda: enhancement_formatters.enhancements_shield(root),
        lambda: enhancement_formatters.enhancements_cooler(root),
        lambda: enhancement_formatters.enhancements_powerplant(root),
        lambda: enhancement_formatters.enhancements_quantum_drive(root),
        lambda: enhancement_formatters.enhancements_radar(root),
        lambda: enhancement_formatters.enhancements_missile(root),
        lambda: enhancement_formatters.enhancements_mission(root, {}),
        lambda: enhancement_formatters.enhancements_weapon(root, {}, None),
        lambda: enhancement_formatters.enhancements_fps_attachment(root),
    ]

    for fmt in formatters:
        result = fmt()
        assert isinstance(result, str), f"Formatter {fmt} returned {type(result)} instead of str"


# ── XML Parsing Edge Cases ────────────────────────────────────────────────────


def test_formatters_handle_unicode_in_attributes():
    """Formatters handle unicode characters in XML attributes."""
    root = _xml("<Entity><Shield MaxHealth='1000' Name='Schildσ'/></Entity>")
    result = enhancement_formatters.enhancements_shield(root)
    assert isinstance(result, str)


def test_formatters_handle_very_large_numbers():
    """Formatters handle very large numeric values."""
    root = _xml("<Entity><Shield MaxHealth='999999999999'/></Entity>")
    result = enhancement_formatters.enhancements_shield(root)
    assert isinstance(result, str)


def test_formatters_handle_scientific_notation():
    """Formatters handle scientific notation in attributes."""
    root = _xml("<Entity><Shield MaxHealth='1.5e6'/></Entity>")
    result = enhancement_formatters.enhancements_shield(root)
    assert isinstance(result, str)


# ── Write Function Edge Cases ────────────────────────────────────────────────


def test_write_ini_creates_parent_directories(gen_module, tmp_path):
    """write_ini creates parent directories if they don't exist."""
    nested_path = tmp_path / "nested" / "dirs" / "output.ini"
    gen_module.write_ini(nested_path, {"key": "value"})
    assert nested_path.exists()
    assert nested_path.read_text(encoding="utf-8") == "key=value"


def test_write_ini_empty_dict(gen_module, tmp_path):
    """write_ini handles empty dict gracefully."""
    output_file = tmp_path / "empty_output.ini"
    gen_module.write_ini(output_file, {})
    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8") == ""


def test_write_ini_sorts_entries(gen_module, tmp_path):
    """write_ini sorts entries alphabetically."""
    output_file = tmp_path / "sorted.ini"
    gen_module.write_ini(output_file, {"zebra": "last", "alpha": "first", "middle": "mid"})
    content = output_file.read_text(encoding="utf-8")
    lines = content.split("\n")
    assert lines == ["alpha=first", "middle=mid", "zebra=last"]
