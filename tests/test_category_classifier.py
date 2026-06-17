"""Tests for src.utils.category_classifier._extract_category_impl.

Key examples sourced from the stock base.ini cache — real SC key patterns.
"""

import pytest
from src.utils.category_classifier import _extract_category_impl

pytestmark = pytest.mark.unit


class TestCategoryClassifierShips:
    def test_vehicle_name_prefix(self):
        assert _extract_category_impl("vehicle_NameANVL_Carrack") == "Ships"

    def test_vehicle_desc_prefix(self):
        assert _extract_category_impl("vehicle_DescANVL_Carrack") == "Ships"

    def test_collector_ship_mod_vehicle_name(self):
        # TheCollector_ShipMod_F7_Hornet_VehicleName — real key from base.ini
        assert _extract_category_impl("TheCollector_ShipMod_F7_Hornet_VehicleName") == "Ships"

    def test_collector_ship_mod_vehicle_name_short(self):
        assert _extract_category_impl("TheCollector_ShipMod_F7_Hornet_VehicleNameShort") == "Ships"

    def test_collector_ship_mod_vehicle_desc(self):
        assert _extract_category_impl("TheCollector_ShipMod_MISC_Fortune_VehicleDesc") == "Ships"


class TestCategoryClassifierShipItems:
    def test_turret_is_ship_item(self):
        # item_Name_Turret_AI — real key from base.ini
        assert _extract_category_impl("item_Name_Turret_AI") == "Ship Items"

    def test_turret_manned(self):
        assert _extract_category_impl("item_Name_Turret_Manned") == "Ship Items"

    def test_shld_component_no_sep(self):
        # item_NameSHLD_AEGS_S04_Idris — real key from base.ini
        assert _extract_category_impl("item_NameSHLD_AEGS_S04_Idris") == "Ship Items"

    def test_powr_component(self):
        assert _extract_category_impl("item_NamePOWR_TR1_PowerPlant") == "Ship Items"

    def test_item_name_uppercase_after_prefix(self):
        # item_NameBEHR_* pattern — uppercase after item_Name → Ship Items
        assert _extract_category_impl("item_NameBEHR_Ballista_S1") == "Ship Items"

    def test_item_mining_non_gadget(self):
        # item_Mining_Consumable_Brandt — real key from base.ini
        assert _extract_category_impl("item_Mining_Consumable_Brandt") == "Ship Items"


class TestCategoryClassifierGear:
    def test_fps_rifle_word(self):
        assert _extract_category_impl("item_Name_behring_P4AR_rifle_weapon_01") == "Gear"

    def test_lowercase_fps_prefix(self):
        # item_Name_adv_agent_core — real key from base.ini
        assert _extract_category_impl("item_Name_adv_agent_core") == "Gear"

    def test_armor_word(self):
        assert _extract_category_impl("item_Name_behr_armor_01") == "Gear"

    def test_item_name_lowercase_after_prefix(self):
        # item_Namebehr_* lowercase → Gear
        assert _extract_category_impl("item_Namebehr_rifle_01") == "Gear"

    def test_item_mining_gadget(self):
        # item_Mining_Gadget_Gadget1 — real key from base.ini
        assert _extract_category_impl("item_Mining_Gadget_Gadget1") == "Gear"

    def test_item_mining_gadget_desc(self):
        assert _extract_category_impl("item_Mining_Gadget_Gadget1_Desc") == "Gear"


class TestCategoryClassifierCommodities:
    def test_commodities_prefix(self):
        assert _extract_category_impl("items_commodities_AluminumOre") == "Commodities"


class TestCategoryClassifierJournal:
    def test_journal_keyword(self):
        # BHG_ReputationJournal_CS3_BodyText — real key from base.ini
        assert _extract_category_impl("BHG_ReputationJournal_CS3_BodyText") == "Journal"

    def test_lowercase_journal_key(self):
        assert _extract_category_impl("some_journal_entry") == "Journal"


class TestCategoryClassifierMissions:
    def test_adagio_prefix(self):
        assert _extract_category_impl("Adagio_Industrial_Salvage_001") == "Missions"

    def test_bounty_prefix(self):
        assert _extract_category_impl("Bounty_Target_Kill_001") == "Missions"

    def test_contract_prefix(self):
        assert _extract_category_impl("contract_001_name") == "Missions"


class TestCategoryClassifierOther:
    def test_empty_key(self):
        assert _extract_category_impl("") == "Other"

    def test_unrecognised_key(self):
        assert _extract_category_impl("UI_SomeButton_Label") == "Other"

    def test_numeric_key(self):
        assert _extract_category_impl("2019_Ann_Sale_Day1") == "Other"
