from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "generate_enhancements_ini.py"
_CATEGORIES = {"fps_armor_descs", "fps_weapon_descs", "fps_attachment_descs"}
_SHIP_FUEL_CATEGORY = {"ship_fuel_descs"}


@pytest.fixture(scope="module")
def gen_module():
    spec = importlib.util.spec_from_file_location("generate_enhancements_ini_e2e_test", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, xml: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")


def _armor(key: str, emission: str, weighted: str = "0") -> str:
    return (
        f'<EntityClassDefinition.Example><Localization Description="@{key}"/>'
        f'<ItemSuitArmorSignatureParams signatureType="Infrared" signatureEmission="{emission}" '
        f'signatureReductionWeighted="{weighted}" signatureReductionAbsolute="0"/>'
        "</EntityClassDefinition.Example>"
    )


@pytest.fixture
def forge(tmp_path):
    forge_dir = tmp_path / "dataforge"
    records = forge_dir / "raw" / "libs" / "foundry" / "records"
    human = records / "entities" / "scitem" / "characters" / "human"
    _write(human / "armor" / "set_arms.xml", _armor("shared_set_desc", "20"))
    _write(human / "starwear" / "helmet" / "set_helmet.xml", _armor("shared_set_desc", "2"))
    _write(human / "armor" / "core.xml", _armor("core_desc", "30", weighted="46.6"))
    _write(
        records / "entities" / "scitem" / "weapons" / "fps_weapons" / "rifle.xml",
        '<EntityClassDefinition.Rifle><Localization Description="@rifle_desc"/><fireActions>'
        '<SWeaponActionFireRapidParams name="Rapid" fireRate="375"/>'
        '<SWeaponActionFireSingleParams name="Single" fireRate="300"/>'
        "</fireActions></EntityClassDefinition.Rifle>",
    )
    modifier_dir = records / "entities" / "scitem" / "weapons" / "weapon_modifier"
    _write(
        modifier_dir / "klwe_ubarrel_flsh_s1.xml",
        '<EntityClassDefinition.Flashlight><Localization Description="@flashlight_desc"/>'
        '<SItemPortLoadoutEntryParams itemPortName="light_1" '
        'entityClassName="weapon_underbarrel_light_narrow_blue_01"/>'
        "</EntityClassDefinition.Flashlight>",
    )
    _write(
        modifier_dir / "weapon_underbarrel_light_narrow_blue_01.xml",
        "<EntityClassDefinition.weapon_underbarrel_light_narrow_blue_01>"
        '<sizeParams lightRadius="35"/><defaultState intensity="3"/>'
        "</EntityClassDefinition.weapon_underbarrel_light_narrow_blue_01>",
    )
    _write(
        records / "entities" / "scitem" / "ships" / "fuel_intakes" / "intake.xml",
        '<EntityClassDefinition.Intake><Localization Description="@intake_desc"/>'
        '<AttachDef Type="Fuel Intake" Size="S2" Grade="A"/>'
        '<SCItemFuelIntakeParams fuelPushRate="32" minimumRate="6"/>'
        '<ItemResourceDeltaStorage><generation resource="Fuel"><resourceAmountPerSecond>'
        '<SStandardResourceUnit standardResourceUnits="2"/>'
        '</resourceAmountPerSecond></generation><consumption resource="Fuel">'
        '<resourceAmountPerSecond><SStandardResourceUnit standardResourceUnits="1"/>'
        "</resourceAmountPerSecond></consumption></ItemResourceDeltaStorage>"
        "</EntityClassDefinition.Intake>",
    )
    _write(
        records / "entities" / "scitem" / "ships" / "fueltanks" / "tank.xml",
        '<EntityClassDefinition.FuelTank><Localization Description="@tank_desc"/>'
        '<SCItemFuelTankParams hydrogenMaxFlowMultiplier="2.6" quantumMaxFlowMultiplier="1.4"/>'
        '<ResourceContainer><capacity><SStandardResourceUnit standardResourceUnits="128"/>'
        "</capacity></ResourceContainer></EntityClassDefinition.FuelTank>",
    )
    base_ini = tmp_path / "out" / "base.ini"
    base_ini.parent.mkdir()
    base_ini.write_text(
        "shared_set_desc=Shared set\ncore_desc=Core armor\nrifle_desc=Rifle\nflashlight_desc=Flashlight\n"
        "intake_desc=Stock intake\ntank_desc=Stock tank\n",
        encoding="utf-8",
    )
    return forge_dir, base_ini


def _read_outputs(gen_module, output_dir: Path) -> dict[str, str]:
    return {
        name: (output_dir / name).read_text(encoding="utf-8")
        for key, name in gen_module.ENHANCEMENT_OUTPUT_FILES.items()
        if key in _CATEGORIES
    }


def test_generator_main_writes_armor_and_weapon_outputs(gen_module, forge):
    forge_dir, base_ini = forge

    gen_module.main(base_ini, forge_dir=forge_dir, categories=_CATEGORIES, max_workers=1)

    outputs = _read_outputs(gen_module, base_ini.parent)
    armor = gen_module.parse_ini(base_ini.parent / gen_module.ENHANCEMENT_OUTPUT_FILES["fps_armor_descs"])
    weapons = gen_module.parse_ini(base_ini.parent / gen_module.ENHANCEMENT_OUTPUT_FILES["fps_weapon_descs"])
    attachments = gen_module.parse_ini(base_ini.parent / gen_module.ENHANCEMENT_OUTPUT_FILES["fps_attachment_descs"])

    assert "shared_set_desc" not in armor
    assert "Weighted Reduction: 46.6" in armor["core_desc"]
    assert "Fire Rate: Auto 375 / Semi-Auto 300 RPM" in weapons["rifle_desc"]
    assert "Narrow Beam: Radius: 35 m  |  Intensity: 3  |  Colour: Blue" in attachments["flashlight_desc"]
    assert all(text for text in outputs.values())


def test_generator_main_output_is_stable_across_runs(gen_module, forge):
    forge_dir, base_ini = forge

    gen_module.main(base_ini, forge_dir=forge_dir, categories=_CATEGORIES, max_workers=1)
    first = _read_outputs(gen_module, base_ini.parent)
    gen_module.main(base_ini, forge_dir=forge_dir, categories=_CATEGORIES, max_workers=1)

    assert _read_outputs(gen_module, base_ini.parent) == first


def test_generator_main_writes_ship_fuel_outputs(gen_module, forge):
    forge_dir, base_ini = forge

    gen_module.main(base_ini, forge_dir=forge_dir, categories=_SHIP_FUEL_CATEGORY, max_workers=1)

    output_path = base_ini.parent / gen_module.ENHANCEMENT_OUTPUT_FILES["ship_fuel_descs"]
    output = gen_module.parse_ini(output_path)

    assert output["intake_desc"].startswith("Stock intake")
    assert "Intake: Push Rate: 32  |  Min Rate: 6" in output["intake_desc"]
    assert "Fuel Delta: +2/s  |  -1/s" in output["intake_desc"]
    assert output["tank_desc"].startswith("Stock tank")
    assert "Flow Mult: Hydrogen Flow: x3  |  Quantum Flow: x1" in output["tank_desc"]
    assert "Capacity: 128" in output["tank_desc"]
