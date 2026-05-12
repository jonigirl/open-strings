"""Tests for mission turret detection in generate_enhancements_ini.

Two CIG signal sources, confirmed by inspecting the live 4.7 DataForge cache:
- SpawnDescription_ShipGroup Name="Turrets" — spawn-data path (~119/2558 missions)
- MissionProperty missionVariableName="OverrideTurretHosility_BP"
  (note CIG's "Hosility" typo) — explicit-hostility-override path (~8 missions)
"""

from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "generate_enhancements_ini.py"


@pytest.fixture(scope="module")
def gen_module():
    spec = importlib.util.spec_from_file_location("generate_enhancements_ini_test_turrets", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_root(body: str) -> ET.Element:
    """Parse an XML fragment wrapped in a synthetic root element."""
    return ET.fromstring(f"<MissionBrokerEntry>{body}</MissionBrokerEntry>")


# ── No turret references ──────────────────────────────────────────────────────
def test_no_turret_references_returns_none(gen_module):
    """Mission with neither spawn group nor override property → None."""
    root = _make_root(
        "<spawnDescriptions>"
        '<SpawnDescription_ShipGroup Name="Hostiles">'
        '<ships><SpawnDescription_Ship concurrentAmount="3"/></ships>'
        "</SpawnDescription_ShipGroup>"
        "</spawnDescriptions>"
    )
    assert gen_module._extract_turret_info(root) is None


# ── Spawn-group turrets (the common case) ─────────────────────────────────────
def test_spawn_group_turrets_default_hostile(gen_module):
    """Turret spawn group with no explicit override → hostile (default)."""
    root = _make_root(
        "<spawnDescriptions>"
        '<SpawnDescription_ShipGroup Name="Turrets">'
        "<ships>"
        '<SpawnDescription_Ship concurrentAmount="3"/>'
        '<SpawnDescription_Ship concurrentAmount="2"/>'
        "</ships>"
        "</SpawnDescription_ShipGroup>"
        "</spawnDescriptions>"
    )
    assert gen_module._extract_turret_info(root) == "5 (hostile)"


def test_perimeter_turrets_naming_variant(gen_module):
    """Name="PerimeterTurrets" — contains 'turret' as substring → detected."""
    root = _make_root(
        "<spawnDescriptions>"
        '<SpawnDescription_ShipGroup Name="PerimeterTurrets">'
        '<ships><SpawnDescription_Ship concurrentAmount="4"/></ships>'
        "</SpawnDescription_ShipGroup>"
        "</spawnDescriptions>"
    )
    assert gen_module._extract_turret_info(root) == "4 (hostile)"


def test_zero_count_with_no_override_returns_none(gen_module):
    """Zero concurrentAmount and no override → None (no turret data)."""
    root = _make_root(
        "<spawnDescriptions>"
        '<SpawnDescription_ShipGroup Name="Turrets">'
        '<ships><SpawnDescription_Ship concurrentAmount="0"/></ships>'
        "</SpawnDescription_ShipGroup>"
        "</spawnDescriptions>"
    )
    assert gen_module._extract_turret_info(root) is None


# ── Explicit hostility override ───────────────────────────────────────────────
def test_explicit_hostile_override_with_count(gen_module):
    """OverrideTurretHosility_BP=1 + spawn count → "(hostile)" qualifier."""
    root = _make_root(
        '<MissionProperty missionVariableName="OverrideTurretHosility_BP">'
        '<value><MissionPropertyValue_Boolean value="1"/></value>'
        "</MissionProperty>"
        "<spawnDescriptions>"
        '<SpawnDescription_ShipGroup Name="Turrets">'
        '<ships><SpawnDescription_Ship concurrentAmount="2"/></ships>'
        "</SpawnDescription_ShipGroup>"
        "</spawnDescriptions>"
    )
    assert gen_module._extract_turret_info(root) == "2 (hostile)"


def test_explicit_friendly_override(gen_module):
    """OverrideTurretHosility_BP=0 + spawn count → "(friendly)" qualifier."""
    root = _make_root(
        '<MissionProperty missionVariableName="OverrideTurretHosility_BP">'
        '<value><MissionPropertyValue_Boolean value="0"/></value>'
        "</MissionProperty>"
        "<spawnDescriptions>"
        '<SpawnDescription_ShipGroup Name="Turrets">'
        '<ships><SpawnDescription_Ship concurrentAmount="3"/></ships>'
        "</SpawnDescription_ShipGroup>"
        "</spawnDescriptions>"
    )
    assert gen_module._extract_turret_info(root) == "3 (friendly)"


def test_override_only_without_spawn_count(gen_module):
    """Override present but no spawn group → 'present (hostile)'."""
    root = _make_root(
        '<MissionProperty missionVariableName="OverrideTurretHosility_BP">'
        '<value><MissionPropertyValue_Boolean value="1"/></value>'
        "</MissionProperty>"
    )
    assert gen_module._extract_turret_info(root) == "present (hostile)"


# ── Interaction with _extract_spawn_counts ────────────────────────────────────
def test_turrets_excluded_from_enemy_count(gen_module):
    """Turret ship-groups should NOT inflate the Enemies tally; otherwise the
    MISSION DETAILS block would double-count them (once as Enemies, once as Turrets)."""
    root = _make_root(
        "<spawnDescriptions>"
        '<SpawnDescription_ShipGroup Name="Hostiles">'
        '<ships><SpawnDescription_Ship concurrentAmount="4"/></ships>'
        "</SpawnDescription_ShipGroup>"
        '<SpawnDescription_ShipGroup Name="Turrets">'
        '<ships><SpawnDescription_Ship concurrentAmount="3"/></ships>'
        "</SpawnDescription_ShipGroup>"
        "</spawnDescriptions>"
    )
    _, num_enemies, _ = gen_module._extract_spawn_counts(root)
    assert num_enemies == 4  # turrets NOT counted here
    assert gen_module._extract_turret_info(root) == "3 (hostile)"
