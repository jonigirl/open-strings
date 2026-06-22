from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from src.utils import enhancement_formatters
from src.utils.app_constants import ENHANCEMENTS_FILES

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "generate_enhancements_ini.py"


@pytest.fixture(scope="module")
def gen_module():
    spec = importlib.util.spec_from_file_location("generate_enhancements_ini_contract_test", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _xml(s: str) -> ET.Element:
    return ET.fromstring(s)


def test_enhancement_output_map_matches_app_constants(gen_module):
    assert gen_module.ENHANCEMENT_OUTPUT_FILES == ENHANCEMENTS_FILES


def test_enhancement_output_files_have_expected_suffix(gen_module):
    for file_name in gen_module.ENHANCEMENT_OUTPUT_FILES.values():
        assert file_name.endswith("_enhancements.ini")


@pytest.mark.parametrize(
    "formatter_call",
    [
        lambda m, r: m.enhancements_shield(r),
        lambda m, r: m.enhancements_missile(r),
        lambda m, r: m.enhancements_radar(r),
        lambda m, r: m.enhancements_cooler(r),
        lambda m, r: m.enhancements_powerplant(r),
        lambda m, r: m.enhancements_quantum_drive(r),
        lambda m, r: m.enhancements_mission(r, {}),
        lambda m, r: m.enhancements_weapon(r, {}, None),
        lambda m, r: m.enhancements_fps_attachment(r),
        lambda m, r: m.enhancements_ship_fuel(r),
        lambda m, r: m.enhancements_countermeasure(r),
        lambda m, r: m.enhancements_lifesupport(r),
        lambda m, r: m.enhancements_ship_dataforge(r, None, None, {}),
    ],
)
def test_all_enhancement_formatters_smoke_return_string(gen_module, formatter_call):
    root = _xml("<Entity />")
    result = formatter_call(gen_module, root)
    assert isinstance(result, str)


def test_fps_attachment_formatter_outputs_weapon_mod_line(gen_module):
    root = _xml(
        """
        <Entity>
          <SWeaponModifierComponentParams>
            <weaponStats damageMultiplier="1.2" fireRateMultiplier="0.9">
              <spreadModifier minMultiplier="1.1" additiveModifier="0.2" />
            </weaponStats>
          </SWeaponModifierComponentParams>
          <SHealthComponentParams Health="120" />
        </Entity>
        """
    )
    out = gen_module.enhancements_fps_attachment(root)
    assert "Weapon Mod:" in out
    assert "Spread:" in out
    assert "Component HP:" in out


def test_ship_fuel_formatter_outputs_intake_and_capacity(gen_module):
    root = _xml(
        """
        <Entity>
          <AttachDef Type="Fuel Intake" Size="S2" Grade="A" />
          <SCItemFuelIntakeParams fuelPushRate="32" minimumRate="6" />
          <SCItemFuelTankParams hydrogenMaxFlowMultiplier="1.2" quantumMaxFlowMultiplier="0.8" />
          <ItemResourceDeltaStorage>
            <generation resource="Fuel"><resourceAmountPerSecond><SStandardResourceUnit standardResourceUnits="2" /></resourceAmountPerSecond></generation>
            <consumption resource="Fuel"><resourceAmountPerSecond><SStandardResourceUnit standardResourceUnits="1" /></resourceAmountPerSecond></consumption>
          </ItemResourceDeltaStorage>
          <ResourceContainer>
            <capacity><SStandardResourceUnit standardResourceUnits="1500" /></capacity>
          </ResourceContainer>
          <SHealthComponentParams Health="450" />
        </Entity>
        """
    )
    out = gen_module.enhancements_ship_fuel(root)
    assert "Intake:" in out
    assert "Flow Mult:" in out
    assert "Fuel Delta:" in out
    assert "Capacity:" in out


def test_countermeasure_formatter_outputs_ammo_and_system(gen_module):
    root = _xml(
        """
        <Entity>
          <AttachDef Size="S1" Grade="B" />
          <SAmmoContainerComponentParams initialAmmoCount="4" maxAmmoCount="8" maxRestockCount="3" />
          <connectionParams powerActiveCooldown="1.5" heatRateOnline="2.0" maxGlow="0.6" />
          <overclockStats fireRateMultiplier="1.2" heatGenerationMultiplier="0.8" />
          <SHealthComponentParams Health="300" />
        </Entity>
        """
    )
    out = gen_module.enhancements_countermeasure(root)
    assert "Ammo:" in out
    assert "System:" in out
    assert "Modifiers:" in out
    assert "Component HP:" in out


def test_lifesupport_formatter_outputs_generation_and_power(gen_module):
    root = _xml(
        """
        <Entity>
          <ItemResourceDeltaConversion>
            <generation resource="LifeSupport"><resourceAmountPerSecond><SStandardResourceUnit standardResourceUnits="4" /></resourceAmountPerSecond></generation>
            <consumption resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="3" /></resourceAmountPerSecond></consumption>
          </ItemResourceDeltaConversion>
          <itemResourceParams overheatTemperature="1200" overheatWarningTemperature="1000" />
          <CoolingEqualizationRateAtTemperatureDifference coolingEqualizationRate="2" temperatureDifference="15" />
          <SDistortionParams Maximum="500" />
          <SHealthComponentParams Health="900" />
        </Entity>
        """
    )
    out = gen_module.enhancements_lifesupport(root)
    assert "Life Support Output:" in out
    assert "Power Draw:" in out
    assert "Thermals:" in out
    assert "Cooling:" in out
    assert "Max Distortion:" in out


def test_shield_formatter_outputs_core_stats(gen_module):
    root = _xml(
        """
        <Entity>
          <SCItemShieldGeneratorParams MaxShieldHealth="2000" MaxShieldRegen="340" DownedRegenDelay="10" DamagedRegenDelay="4">
            <ShieldResistance>
              <SShieldResistance Min="0.1" Max="0.2" />
              <SShieldResistance Min="-0.7" Max="-0.3" />
            </ShieldResistance>
          </SCItemShieldGeneratorParams>
          <ItemResourceDeltaGeneration>
            <consumption resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="5.5" /></resourceAmountPerSecond></consumption>
          </ItemResourceDeltaGeneration>
          <EMSignature nominalSignature="250" />
          <IRSignature nominalSignature="120" />
          <SHealthComponentParams Health="900" />
        </Entity>
        """
    )
    out = gen_module.enhancements_shield(root)
    assert "Max HP:" in out
    assert "Downed Delay:" in out
    assert "Resist:" in out
    assert "Signatures:" in out
    assert "Power Draw:" in out
    assert "Component HP:" in out


def test_shield_formatter_handles_missing_optional_blocks(gen_module):
    root = _xml(
        """
        <Entity>
          <SCItemShieldGeneratorParams MaxShieldHealth="1500" MaxShieldRegen="250" />
        </Entity>
        """
    )
    out = gen_module.enhancements_shield(root)
    assert "Max HP:" in out
    assert "Resist:" not in out


def test_missile_formatter_outputs_core_metrics(gen_module):
    root = _xml(
        """
        <Entity>
          <MissileProjectile speed="850" lifetime="12" />
          <Tracking guidanceType="Infrared" seekerType="Passive" lockTime="1.5" minLockRange="600" maxLockRange="4500" trackingRange="7000" proximityFuseRange="12" maxGForce="15" turnRate="35" detonationMode="Proximity" />
          <Propulsion acceleration="120" />
          <propellant amount="10" />
          <targetingParams lockRangeMin="500" lockRangeMax="6000" />
          <SCItemMissileParams armTime="1.2" explosionSafetyDistance="150" />
          <GCSParams linearSpeed="900" />
          <damage><DamageInfo DamagePhysical="200" /></damage>
          <ExplosionParams maxRadius="20" />
          <ProjectileParams effectiveRange="3500" />
          <EMSignature nominalSignature="120" />
          <IRSignature nominalSignature="95" />
          <SHealthComponentParams Health="80" />
        </Entity>
        """
    )
    out = gen_module.enhancements_missile(root)
    assert "Velocity:" in out
    assert "Guidance:" in out
    assert "Lock Range:" in out
    assert "Arm Time:" in out
    assert "Damage:" in out
    assert "Blast Radius:" in out
    assert "EM Signature:" in out
    assert "Component HP:" in out


def test_missile_formatter_damage_breakdown_multiple_types(gen_module):
    root = _xml(
        """
        <Entity>
          <damage>
            <DamageInfo DamagePhysical="100" DamageEnergy="50" />
          </damage>
        </Entity>
        """
    )
    out = gen_module.enhancements_missile(root)
    assert "Damage:" in out
    assert "Phys:" in out
    assert "Energy:" in out


def test_missile_formatter_max_lock_range_fallback(gen_module):
    root = _xml(
        """
        <Entity>
          <targetingParams lockRangeMax="800" />
          <SCItemMissileParams armTime="1" />
        </Entity>
        """
    )
    out = gen_module.enhancements_missile(root)
    assert "Max Lock Range:" in out
    assert "Arm Time:" in out


def test_missile_formatter_min_lock_range_only(gen_module):
    root = _xml(
        """
        <Entity>
          <targetingParams lockRangeMin="650" />
        </Entity>
        """
    )
    out = gen_module.enhancements_missile(root)
    assert "Min Lock Range:" in out


def test_missile_formatter_handles_fallback_damage_and_invalid_numeric_fields(gen_module):
    root = _xml(
        """
        <Entity>
          <DamageInfo DamagePhysical="25" />
          <targetingParams lockRangeMin="bad" lockRangeMax="also_bad" />
          <ExplosionParams maxRadius="bad" />
          <ProjectileParams effectiveRange="bad" />
          <EMSignature nominalSignature="bad" />
          <IRSignature nominalSignature="bad" />
        </Entity>
        """
    )
    out = gen_module.enhancements_missile(root)
    assert "Damage:" in out
    assert "Lock Range:" not in out


def test_radar_formatter_outputs_range_mode_and_power(gen_module):
    root = _xml(
        """
        <Entity>
          <aimAssist distanceMinAssignment="600" distanceMaxAssignment="2500" />
          <pingProperties cooldownTime="2.5" />
          <SCItemRadarSignatureDetection permitPassiveDetection="1" permitActiveDetection="1" />
          <ItemResourceDeltaGeneration>
            <consumption resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="3.2" /></resourceAmountPerSecond></consumption>
          </ItemResourceDeltaGeneration>
          <SHealthComponentParams Health="700" />
        </Entity>
        """
    )
    out = gen_module.enhancements_radar(root)
    assert "Aim Assist Range:" in out
    assert "Ping Cooldown:" in out
    assert "Detection Mode:" in out
    assert "Power Draw:" in out
    assert "Component HP:" in out


def test_radar_formatter_handles_invalid_aim_and_ping_values(gen_module):
    root = _xml(
        """
        <Entity>
          <aimAssist distanceMinAssignment="bad" distanceMaxAssignment="bad" />
          <pingProperties cooldownTime="bad" />
          <SCItemRadarSignatureDetection permitPassiveDetection="1" />
        </Entity>
        """
    )
    out = gen_module.enhancements_radar(root)
    assert "Aim Assist Range:" not in out
    assert "Ping Cooldown:" not in out
    assert "Detection Mode: Passive" in out


def test_mission_formatter_outputs_core_blocks(gen_module):
    root = _xml(
        """
        <MissionBrokerEntry description="@GoblinG_ArcCorp_RecoverCargoFPS_L_Title" linkedMission="123" tutorial="1" onceOnly="1" missionDifficulty="4">
          <missionResultReputationRewards>
            <SReputationAmountListParams>
              <SReputationAmountParams reputationScope="primary" reward="rep_reward_1" />
            </SReputationAmountListParams>
          </missionResultReputationRewards>
          <SpawnDescription_ShipGroup Name="enemy wave">
            <SpawnDescription_Ship concurrentAmount="2" />
          </SpawnDescription_ShipGroup>
          <SpawnDescription_NPC_Group Name="soldier x 3" />
          <SpawnDescription_ShipGroup Name="Turrets">
            <SpawnDescription_Ship concurrentAmount="2" />
          </SpawnDescription_ShipGroup>
        </MissionBrokerEntry>
        """
    )
    out = gen_module.enhancements_mission(root, {"rep_reward_1": 250})
    assert "Engagement Type:" in out
    assert "Mission Type:" in out
    assert "Difficulty (1-7):" in out
    assert "Reputation XP:" in out
    assert "Enemies:" in out
    assert "Turrets:" in out


def test_weapon_formatter_outputs_damage_and_range(gen_module):
    weapon_root = _xml(
        """
        <Entity>
          <WeaponActionFire fireRate="600" name="rapid" />
          <SHealthComponentParams Health="120" />
          <EMSignature nominalSignature="55" />
          <IRSignature nominalSignature="42" />
          <itemResourceParams overheatTemperature="12000" />
          <SAmmoContainerComponentParams ammoParamsRecord="ammo-guid" maxAmmoCount="30" />
          <SWeaponRegenConsumerParams requestedRegenPerSec="2" regenerationCooldown="1.5" regenerationCostPerBullet="1" maxAmmoLoad="80" />
          <ItemResourceDeltaGeneration>
            <consumption resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="2" /></resourceAmountPerSecond></consumption>
          </ItemResourceDeltaGeneration>
          <RigidPhysics Mass="18" />
          <SProjectileLauncher pelletCount="2" />
        </Entity>
        """
    )
    ammo_root = _xml(
        """
        <Ammo>
          <damage>
            <DamageInfo DamagePhysical="50" DamageEnergy="20" />
          </damage>
          <DamageInfo DamagePhysical="5" />
          <Projectile speed="900" lifetime="2" />
          <damageDropMinDistance><DamageInfo DamagePhysical="20" DamageEnergy="10" /></damageDropMinDistance>
          <damageDropPerMeter><DamageInfo DamagePhysical="1" DamageEnergy="0.5" /></damageDropPerMeter>
          <damageDropMinDamage><DamageInfo DamagePhysical="5" DamageEnergy="2" /></damageDropMinDamage>
        </Ammo>
        """
    )
    out = gen_module.enhancements_weapon(weapon_root, {"ammo-guid": ammo_root}, {}, None)
    assert "Fire Rate:" in out
    assert "Alpha Dmg:" in out
    assert "DPS:" in out
    assert "Full Dmg to:" in out
    assert "Power Draw:" in out
    assert "Overheat Temp:" in out


def test_ship_dataforge_formatter_outputs_flight_and_insurance(gen_module):
    ship_root = _xml(
        """
        <Entity>
          <VehicleComponentParams crewSize="3" vehicleCareer="@CAREER_FIGHTER" vehicleRole="@ROLE_HEAVY">
            <maxBoundingBoxSize y="48" />
          </VehicleComponentParams>
          <shipInsuranceParams baseWaitTimeMinutes="12" mandatoryWaitTimeMinutes="3" />
          <SItemPortLoadoutEntryParams itemPortName="hardpoint_armor" entityClassName="ARMOR_CLASS_A" />
        </Entity>
        """
    )
    controller_root = _xml(
        """
        <Controller>
          <IFCSParams scmSpeed="220" maxSpeed="1180" boostSpeedForward="300" boostSpeedBackward="80" />
          <SIFCSSpeedProfile>
            <angularVelocity x="35" y="90" z="30" />
          </SIFCSSpeedProfile>
        </Controller>
        """
    )
    armor_root = _xml(
        """
        <Armor>
          <SHealthComponentParams Health="2000" />
        </Armor>
        """
    )
    out = gen_module.enhancements_ship_dataforge(
        ship_root,
        controller_root,
        {"CAREER_FIGHTER": "Fighter", "ROLE_HEAVY": "Heavy"},
        {"armor_class_a": armor_root},
    )
    assert "SCM:" in out
    assert "Boost:" in out
    assert "Pitch:" in out
    assert "Crew:" in out
    assert "Class:" in out
    assert "Role:" in out
    assert "Armor HP:" in out
    assert "Insurance:" in out


def test_cooler_formatter_outputs_cooling_and_power(gen_module):
    root = _xml(
        """
        <Entity>
          <ItemResourceDeltaGeneration>
            <generation resource="Coolant"><resourceAmountPerSecond><SStandardResourceUnit standardResourceUnits="350" /></resourceAmountPerSecond></generation>
            <consumption resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="2.4" /></resourceAmountPerSecond></consumption>
          </ItemResourceDeltaGeneration>
          <itemResourceParams overheatTemperature="9000" />
          <SHealthComponentParams Health="1200" />
        </Entity>
        """
    )
    out = gen_module.enhancements_cooler(root)
    assert "Cooling Rate:" in out
    assert "Power Draw:" in out
    assert "Overheat Temp:" in out
    assert "Component HP:" in out


def test_powerplant_formatter_outputs_power_and_distortion(gen_module):
    root = _xml(
        """
        <Entity>
          <ItemResourceDeltaGeneration>
            <generation resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="18.5" /></resourceAmountPerSecond></generation>
          </ItemResourceDeltaGeneration>
          <itemResourceParams overheatTemperature="12000" />
          <SDistortionParams Maximum="650" />
          <SHealthComponentParams Health="1500" />
        </Entity>
        """
    )
    out = gen_module.enhancements_powerplant(root)
    assert "Power Output:" in out
    assert "Overheat Temp:" in out
    assert "Max Distortion:" in out
    assert "Component HP:" in out


def test_quantum_drive_formatter_outputs_core_metrics(gen_module):
    root = _xml(
        """
        <Entity>
          <SCItemQuantumDriveParams quantumFuelRequirement="0.0042" />
          <params __type="SQuantumDriveParams" driveSpeed="210000000" spoolUpTime="3" cooldownTime="9.5" calibrationRate="0.8" minCalibrationRequirement="100" maxCalibrationRequirement="500" stageOneAccelRate="12" stageTwoAccelRate="25" />
          <ItemResourceDeltaConversion>
            <consumption resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="4" /></resourceAmountPerSecond></consumption>
            <consumption resource="QuantumFuel"><resourceAmountPerSecond><SStandardResourceUnit standardResourceUnits="1.5" /></resourceAmountPerSecond></consumption>
          </ItemResourceDeltaConversion>
          <itemResourceParams overheatTemperature="18000" />
          <SDistortionParams Maximum="500" />
          <SHealthComponentParams Health="1000" />
        </Entity>
        """
    )
    out = gen_module.enhancements_quantum_drive(root)
    assert "QT Speed:" in out
    assert "Fuel/Gm:" in out
    assert "QT Fuel Use:" in out
    assert "Power Draw:" in out
    assert "Max Distortion:" in out


def test_quantum_drive_formatter_supports_tag_type_and_missing_spool(gen_module):
    root = _xml(
        """
        <Entity>
          <SCItemQuantumDriveParams quantumFuelRequirement="0.0010" />
          <SQuantumDriveParams driveSpeed="100000000" calibrationRate="0.5" />
        </Entity>
        """
    )
    out = gen_module.enhancements_quantum_drive(root)
    assert "QT Speed:" in out
    assert "Spool: ?" in out
    assert "Cal Rate:" in out


def test_cooler_formatter_skips_placeholder_overheat(gen_module):
    root = _xml(
        """
        <Entity>
          <ItemResourceDeltaGeneration>
            <generation resource="Coolant"><resourceAmountPerSecond><SStandardResourceUnit standardResourceUnits="120" /></resourceAmountPerSecond></generation>
          </ItemResourceDeltaGeneration>
          <itemResourceParams overheatTemperature="450000" />
        </Entity>
        """
    )
    out = gen_module.enhancements_cooler(root)
    assert "Cooling Rate:" in out
    assert "Overheat Temp:" not in out


def test_powerplant_formatter_includes_non_numeric_overheat(gen_module):
    root = _xml(
        """
        <Entity>
          <ItemResourceDeltaGeneration>
            <generation resource="Power"><resourceAmountPerSecond><SPowerSegmentResourceUnit units="9" /></resourceAmountPerSecond></generation>
          </ItemResourceDeltaGeneration>
          <itemResourceParams overheatTemperature="N/A" />
        </Entity>
        """
    )
    out = gen_module.enhancements_powerplant(root)
    assert "Power Output:" in out
    assert "Overheat Temp:" in out


def test_script_formatters_are_bound_to_extracted_module(gen_module):
    assert gen_module.enhancements_shield is enhancement_formatters.enhancements_shield
    assert gen_module.enhancements_missile is enhancement_formatters.enhancements_missile
    assert gen_module.enhancements_radar is enhancement_formatters.enhancements_radar
    assert gen_module.enhancements_mission is enhancement_formatters.enhancements_mission
    assert gen_module.enhancements_weapon is enhancement_formatters.enhancements_weapon
    assert gen_module.enhancements_ship_dataforge is enhancement_formatters.enhancements_ship_dataforge
    assert gen_module.enhancements_fps_attachment is enhancement_formatters.enhancements_fps_attachment
    assert gen_module.enhancements_ship_fuel is enhancement_formatters.enhancements_ship_fuel
    assert gen_module.enhancements_countermeasure is enhancement_formatters.enhancements_countermeasure
    assert gen_module.enhancements_lifesupport is enhancement_formatters.enhancements_lifesupport
    assert gen_module.enhancements_cooler is enhancement_formatters.enhancements_cooler
    assert gen_module.enhancements_powerplant is enhancement_formatters.enhancements_powerplant
    assert gen_module.enhancements_quantum_drive is enhancement_formatters.enhancements_quantum_drive
