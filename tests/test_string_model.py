"""Additional tests for src/models/string_model.py.

Covers gaps in existing test_core.py:
- StringEntry.is_modified property
- More extract_category edge cases:
  * item_mining_gadget_ → Gear
  * item_mining_ (non-gadget) → Ship Items
  * journal key → Journal
  * vehicle_name ending _vehiclename/_vehicledesc/_vehiclenameshort → Ships
  * empty key → Other
  * _determine_status_from_source and __post_init__ status override
"""

import pytest
from src.models.string_model import StringEntry


@pytest.mark.unit
class TestIsModified:
    """StringEntry.is_modified reflects whether custom differs from original."""

    def test_empty_custom_is_not_modified(self):
        e = StringEntry(key="k", source_file="global", original_value="orig", custom_value="")
        assert e.is_modified is False

    def test_custom_same_as_original_is_not_modified(self):
        e = StringEntry(key="k", source_file="global", original_value="same", custom_value="same")
        assert e.is_modified is False

    def test_custom_different_from_original_is_modified(self):
        e = StringEntry(key="k", source_file="global", original_value="orig", custom_value="custom")
        assert e.is_modified is True

    def test_custom_without_original_is_modified(self):
        e = StringEntry(key="k", source_file="user", original_value="", custom_value="new value")
        assert e.is_modified is True

    def test_both_empty_is_not_modified(self):
        e = StringEntry(key="k", source_file="global", original_value="", custom_value="")
        assert e.is_modified is False


@pytest.mark.unit
class TestExtractCategoryEdgeCases:
    """Additional extract_category coverage for previously untested key patterns."""

    def test_empty_key_returns_other(self):
        assert StringEntry.extract_category("") == "Other"

    def test_item_mining_gadget_is_gear(self):
        assert StringEntry.extract_category("item_mining_gadget_ore_scanner") == "Gear"

    def test_item_mining_non_gadget_is_ship_items(self):
        # item_mining_ (without gadget) → Ship Items
        assert StringEntry.extract_category("item_mining_laser_head") == "Ship Items"

    def test_journal_in_key_is_journal(self):
        assert StringEntry.extract_category("journal_entry_pirates") == "Journal"
        assert StringEntry.extract_category("some_journal_thing") == "Journal"

    def test_vehicle_name_ending_vehiclename_is_ships(self):
        # Wikelo ship mods — key ends with _VehicleName
        assert StringEntry.extract_category("TheCollector_ShipMod_001_VehicleName") == "Ships"

    def test_vehicle_name_ending_vehicledesc_is_ships(self):
        assert StringEntry.extract_category("TheCollector_ShipMod_001_VehicleDesc") == "Ships"

    def test_vehicle_name_ending_vehiclenameshort_is_ships(self):
        assert StringEntry.extract_category("TheCollector_ShipMod_001_VehicleNameShort") == "Ships"

    def test_vehicle_desc_prefix_is_ships(self):
        assert StringEntry.extract_category("vehicle_DescANVL_Carrack") == "Ships"

    def test_gmisl_component_is_ship_items(self):
        assert StringEntry.extract_category("item_NameGMISL_Flash") == "Ship Items"

    def test_bomb_component_is_ship_items(self):
        assert StringEntry.extract_category("item_NameBOMB_A03") == "Ship Items"

    def test_misl_component_is_ship_items(self):
        assert StringEntry.extract_category("item_NameMISL_Tempest") == "Ship Items"

    def test_jump_drive_is_ship_items(self):
        assert StringEntry.extract_category("item_NameJUMP_Erebus") == "Ship Items"

    def test_item_name_uppercase_segment_is_ship_items(self):
        # After "item_Name", first char uppercase → Ship Items
        assert StringEntry.extract_category("item_NameBEHR_FPC") == "Ship Items"

    def test_item_name_lowercase_segment_is_gear(self):
        # After "item_Name", first char lowercase → Gear
        assert StringEntry.extract_category("item_Namebehr_FPC") == "Gear"

    def test_turret_is_ship_items(self):
        assert StringEntry.extract_category("item_Name_Turret_S2") == "Ship Items"
        assert StringEntry.extract_category("item_Desc_Turret_Remote") == "Ship Items"

    def test_ship_weapon_xl_size_is_ship_items(self):
        assert StringEntry.extract_category("item_Name_S4_Gatling") == "Ship Items"

    def test_pistol_is_gear(self):
        assert StringEntry.extract_category("item_Name_behr_pistol_ballistic") == "Gear"

    def test_armor_is_gear(self):
        assert StringEntry.extract_category("item_Name_armor_light_duster") == "Gear"

    def test_helmet_is_gear(self):
        assert StringEntry.extract_category("item_Name_helmet_medium") == "Gear"

    def test_commodities_prefix(self):
        assert StringEntry.extract_category("items_commodities_Gold") == "Commodities"

    def test_mission_prefixes_variety(self):
        # Sample of mission prefixes
        for key in (
            "tutorial_intro_step1",
            "bounty_mission_desc",
            "shubin_m01_title",
            "contract_hunt_target",
        ):
            assert StringEntry.extract_category(key) == "Missions", f"Expected Missions for key: {key!r}"


@pytest.mark.unit
class TestStringEntryPostInit:
    """__post_init__ auto-fills category and status when omitted."""

    def test_category_auto_filled_from_key(self):
        e = StringEntry(key="vehicle_NameHunter", source_file="global", original_value="Cutlass")
        assert e.category == "Ships"

    def test_status_auto_filled_unmodified(self):
        e = StringEntry(key="k", source_file="global", original_value="v", custom_value="")
        assert e.status == "Unmodified"

    def test_status_auto_filled_modified(self):
        e = StringEntry(key="k", source_file="global", original_value="v", custom_value="changed")
        assert e.status == "Modified"

    def test_explicit_status_not_overwritten(self):
        # When status is provided, __post_init__ must not change it
        e = StringEntry(key="k", source_file="global", original_value="v", custom_value="", status="New")
        assert e.status == "New"

    def test_explicit_category_not_overwritten(self):
        e = StringEntry(
            key="vehicle_NameHunter",
            source_file="contracts",
            original_value="x",
            category="Missions",
        )
        assert e.category == "Missions"
