"""Tests for the mission Engagement Type classifier in generate_enhancements_ini.

The classifier reads CIG's own loc-key naming convention (FPS / UGF / OnFoot
markers) to tag each mission as "FPS", "Ship", or "FPS & Ship". The result is
prepended to the MISSION DETAILS block so players can see which loadout to
bring before accepting a contract.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "generate_enhancements_ini.py"


@pytest.fixture(scope="module")
def gen_module():
    spec = importlib.util.spec_from_file_location("generate_enhancements_ini_test", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── FPS ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "loc_key",
    [
        "BountyHuntersGuild_FPS_Nyx_title_001",
        "vaughn_assassination_FPS_UGF_legal_title_001",
        "vaughn_assassination_FPS_UGF_legal_boss_desc_001",
        "Bitzeroes_eliminateall_dc_title_001_FPS",
        "PAF_OnFoot_Eliminate_title_001",
        "Shubin_FPS_Rescue_title_001",
    ],
)
def test_classifies_as_fps(gen_module, loc_key):
    assert gen_module._classify_mission_engagement(loc_key) == "FPS"


# ── Ship ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "loc_key",
    [
        "BountyHuntersGuild_Bounty_Stanton_Easy_title_001",
        "ECN_Bounty_Stanton_Easy_title_001",
        "CFP_Delivery_OutpostToStation_title_001",
        "CFP_Delivery_OutpostToTradepost_title_001",
        "Headhunters_RegionA_Pyro_title_001",
        "Bitzeroes_bombingrun_dc_title_001",
        "destroyitem_title_001",
    ],
)
def test_classifies_as_ship(gen_module, loc_key):
    assert gen_module._classify_mission_engagement(loc_key) == "Ship"


# ── FPS & Ship ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "loc_key",
    [
        "GoblinG_ArcCorp_RecoverCargoFPS_L_Title",
        "GoblinG_Crusader_RecoverCargoFPS_S_Title",
        "BHG_FPS_Cargo_Recover_desc",
    ],
)
def test_classifies_as_fps_and_ship(gen_module, loc_key):
    assert gen_module._classify_mission_engagement(loc_key) == "FPS & Ship"


# ── Edge cases ────────────────────────────────────────────────────────────────
def test_empty_loc_key_defaults_to_ship(gen_module):
    """Missing loc_key (rare data bug) shouldn't crash — quietly default."""
    assert gen_module._classify_mission_engagement("") == "Ship"
    assert gen_module._classify_mission_engagement(None) == "Ship"


def test_case_insensitive(gen_module):
    """Matching is lowercased so key casing doesn't shift the answer."""
    assert gen_module._classify_mission_engagement("MISSION_FPS_TITLE") == "FPS"
    assert gen_module._classify_mission_engagement("mission_fps_title") == "FPS"
    assert gen_module._classify_mission_engagement("Mission_Fps_Title") == "FPS"


def test_salvage_with_fps_is_fps_and_ship(gen_module):
    """Salvage token + FPS marker → FPS & Ship (conservative: better to
    over-warn "bring a ship" than under-warn for this category)."""
    result = gen_module._classify_mission_engagement("CFP_Salvage_FPS_title_001")
    assert result == "FPS & Ship"
