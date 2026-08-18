"""Tests for blueprint pool lookup and contract generator blueprint grouping.

Covers three areas from upstream v1.4.0:
- T2-B: component name-tags, CIG size prefix stripping, mining-head fallback
- T2-C: rank-tier sub-section labels and 3-level mission_blueprints structure
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
    spec = importlib.util.spec_from_file_location("generate_enhancements_ini_test_bpools", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helpers for building minimal XML fixtures on disk
# ---------------------------------------------------------------------------


def _write_xml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _bp_xml(ref: str, entity_class: str) -> str:
    return (
        f'<CraftingBlueprintRecord __ref="{ref}">'
        f'<Components><Component __polymorphicType="CraftingProcess_Creation"'
        f' entityClass="{entity_class}"/></Components>'
        f"</CraftingBlueprintRecord>"
    )


def _pool_xml(ref: str, bp_refs: list[str]) -> str:
    rewards = "".join(f'<BlueprintReward blueprintRecord="{r}"/>' for r in bp_refs)
    return f'<BlueprintPoolRecord __ref="{ref}"><blueprintRewards>{rewards}</blueprintRewards></BlueprintPoolRecord>'


def _contractgen_xml(title_key: str, system: str, pool_uuid: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ContractGenerator>
  <ContractGeneratorHandler_List debugName="handler_{system}">
    <Contract debugName="contract_{title_key}_{system}">
      <ContractStringParam param="Title" value="@{title_key}"/>
      <ContractStringParam param="Description" value="@{title_key}_desc"/>
      <BlueprintRewards blueprintPool="{pool_uuid}"/>
    </Contract>
  </ContractGeneratorHandler_List>
</ContractGenerator>
"""


# ---------------------------------------------------------------------------
# TestMultiSourcePoolMerge — scan_contract_generators 3-level structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMultiSourcePoolMerge:
    def test_two_blueprint_rewards_in_one_contract_merge(self, gen_module, tmp_path):
        pool_a = "pool-a-uuid"
        pool_b = "pool-b-uuid"
        blueprint_pools = {
            pool_a: ["Item Alpha", "Item Beta"],
            pool_b: ["Item Gamma"],
        }

        cg_dir = tmp_path / "cg"
        _write_xml(
            cg_dir / "contract_a.xml",
            f"""<?xml version="1.0" encoding="utf-8"?>
<ContractGenerator>
  <ContractGeneratorHandler_List debugName="handler_Stanton">
    <Contract debugName="merge_test_Stanton">
      <ContractStringParam param="Title" value="@merge_title"/>
      <ContractStringParam param="Description" value="@merge_desc"/>
      <BlueprintRewards blueprintPool="{pool_a}"/>
      <BlueprintRewards blueprintPool="{pool_b}"/>
    </Contract>
  </ContractGeneratorHandler_List>
</ContractGenerator>
""",
        )

        missions, mission_blueprints, _chance, _items = gen_module.scan_contract_generators(
            cg_dir, blueprint_pools=blueprint_pools
        )

        per_system = mission_blueprints.get("merge_title", {})
        all_items: list[str] = []
        for label_dict in per_system.get("Stanton", {}).values():
            all_items.extend(label_dict)

        assert "Item Alpha" in all_items
        assert "Item Beta" in all_items
        assert "Item Gamma" in all_items

    def test_merge_dedups_duplicate_items_across_pools(self, gen_module, tmp_path):
        pool_a = "dedup-pool-a"
        pool_b = "dedup-pool-b"
        blueprint_pools = {
            pool_a: ["Shared Item", "Only A"],
            pool_b: ["Shared Item", "Only B"],
        }

        cg_dir = tmp_path / "cg_dedup"
        _write_xml(
            cg_dir / "contract_dedup.xml",
            f"""<?xml version="1.0" encoding="utf-8"?>
<ContractGenerator>
  <ContractGeneratorHandler_List debugName="handler_Stanton">
    <Contract debugName="dupe_test_Stanton">
      <ContractStringParam param="Title" value="@dupe_title"/>
      <ContractStringParam param="Description" value="@dupe_desc"/>
      <BlueprintRewards blueprintPool="{pool_a}"/>
      <BlueprintRewards blueprintPool="{pool_b}"/>
    </Contract>
  </ContractGeneratorHandler_List>
</ContractGenerator>
""",
        )

        _missions, mission_blueprints, _chance, _items = gen_module.scan_contract_generators(
            cg_dir, blueprint_pools=blueprint_pools
        )

        # Items should appear once each at the empty-label bucket
        all_items: list[str] = []
        for label_dict in mission_blueprints.get("dupe_title", {}).get("Stanton", {}).values():
            all_items.extend(label_dict)

        assert all_items.count("Shared Item") == 1
        assert "Only A" in all_items
        assert "Only B" in all_items

    def test_single_pool_unchanged(self, gen_module, tmp_path):
        pool_uuid = "single-pool-uuid"
        blueprint_pools = {pool_uuid: ["Only Item"]}

        cg_dir = tmp_path / "cg_single"
        _write_xml(cg_dir / "contract_single.xml", _contractgen_xml("single_title", "Stanton", pool_uuid))

        _missions, mission_blueprints, _chance, _items = gen_module.scan_contract_generators(
            cg_dir, blueprint_pools=blueprint_pools
        )

        assert mission_blueprints["single_title"]["Stanton"][""] == ["Only Item"]


# ---------------------------------------------------------------------------
# TestBlueprintNameTags — T2-B annotation pipeline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlueprintNameTags:
    def test_scitem_lookup_emits_tag_for_component(self, gen_module, tmp_path):
        """build_scitem_lookups produces entity_name_tags for an item with Class= in desc."""
        scitem_dir = tmp_path / "scitems"
        entity_ref = "comp-uuid-001"
        xml = (
            f'<SCItemVehicleWeaponParams __ref="{entity_ref}">'
            f'<Components><ItemNameParams Name="Laser Cannon" Description="@MyComponent_desc"/></Components>'
            f"</SCItemVehicleWeaponParams>"
        )
        scitem_path = scitem_dir / "mycomponent.xml"
        _write_xml(scitem_path, xml)

        # loc dict must contain the desc key with Class= attribute
        loc_key = "MyComponent_desc"
        loc_value = "Size: 2\nGrade: B\nClass: Laser"
        # build_scitem_lookups takes loc as second arg
        _mag_lookup, _enames, _eby_fn, entity_name_tags = gen_module.build_scitem_lookups(
            scitem_dir, {loc_key: loc_value}
        )

        assert entity_ref in entity_name_tags
        assert entity_name_tags[entity_ref].startswith("[")

    def test_scitem_lookup_skips_tag_for_non_component(self, gen_module, tmp_path):
        """No tag when description doesn't contain Class: annotation."""
        scitem_dir = tmp_path / "scitems_nontag"
        entity_ref = "plain-uuid-002"
        loc_key = "Plain_desc"
        xml = (
            f'<SCItemVehicleWeaponParams __ref="{entity_ref}">'
            f'<Components><ItemNameParams Name="Plain Item" Description="@{loc_key}"/></Components>'
            f"</SCItemVehicleWeaponParams>"
        )
        _write_xml(scitem_dir / "plain.xml", xml)

        _mag, _enames, _eby_fn, entity_name_tags = gen_module.build_scitem_lookups(
            scitem_dir, {loc_key: "A plain description with no structured attributes."}
        )

        assert entity_ref not in entity_name_tags

    def test_blueprint_pool_appends_tag_on_uuid_hit(self, gen_module, tmp_path):
        """When entity_name_tags supplied and UUID resolves, tag appended to display name."""
        entity_uuid = "entity-tag-uuid"
        bp_uuid = "bp-tag-uuid"
        pool_uuid = "pool-tag-uuid"

        bp_dir = tmp_path / "bp"
        pool_dir = tmp_path / "pool"

        _write_xml(bp_dir / "mybp.xml", _bp_xml(bp_uuid, entity_uuid))
        _write_xml(pool_dir / "bp_mypool.xml", _pool_xml(pool_uuid, [bp_uuid]))

        entity_names = {entity_uuid: "Helix I"}
        entity_name_tags = {entity_uuid: "[LASER-S1-B]"}

        pools, _pool_names = gen_module.build_blueprint_pool_lookup(
            pool_dir, bp_dir, entity_names, entity_name_tags=entity_name_tags
        )

        assert pools[pool_uuid] == ["Helix I [LASER-S1-B]"]

    def test_tagger_strict_path_unchanged(self, gen_module):
        """Size + Grade + recognised Class → [ABBREV-Sx-grade] shape."""
        desc = "Size: 2\nGrade: B\nClass: Military"
        tag = gen_module._component_name_tag(desc)
        assert tag == "[MIL-S2-B]"

    def test_tagger_fallback_mining_head_full(self, gen_module):
        """Mining head with S-prefix size, Item Type, and Grade → [TYPE-Sx-grade]."""
        desc = "Size: S0\nItem Type: Mining Laser\nGrade: B"
        tag = gen_module._component_name_tag(desc)
        assert tag == "[MIN-S0-B]"

    def test_tagger_handles_new_class_and_item_type_fallbacks(self, gen_module):
        """New 4.10 component metadata should still produce a compact tag."""
        class_desc = "Size: 2\nGrade: B\nClass: Exploration"
        assert gen_module._component_name_tag(class_desc) == "[EXP-S2-B]"

        type_desc = "Size: S0\nItem Type: Survey Scanner\nGrade: B"
        assert gen_module._component_name_tag(type_desc) == "[SUR-S0-B]"

    def test_tagger_fallback_mining_laser_size_only(self, gen_module):
        """Mining head with S-prefix size + Item Type but no Grade → [TYPE-Sx]."""
        desc = "Size: S0\nItem Type: Mining Laser"
        tag = gen_module._component_name_tag(desc)
        assert tag == "[MIN-S0]"

    def test_tagger_unknown_type_with_grade(self, gen_module):
        """Unknown Item Type absent from _ITEM_TYPE_ABBREV but has Size + Grade → [Sx-grade]."""
        desc = "Size: S3\nGrade: A"
        tag = gen_module._component_name_tag(desc)
        assert tag == "[S3-A]"

    def test_tagger_rejects_size_only_no_grade_no_type(self, gen_module):
        """Size only with no Grade and no known Type → None (not worth emitting)."""
        desc = "Size: S3"
        tag = gen_module._component_name_tag(desc)
        assert tag is None

    def test_tagger_rejects_no_size(self, gen_module):
        """No Size line at all → None."""
        desc = "Grade: A\nClass: Laser"
        tag = gen_module._component_name_tag(desc)
        assert tag is None

    def test_strip_cig_size_prefix_helper(self, gen_module):
        assert gen_module._strip_cig_size_prefix("S0 Helix") == "Helix"
        assert gen_module._strip_cig_size_prefix("S12 Rockhound") == "Rockhound"
        assert gen_module._strip_cig_size_prefix("Sasquatch") == "Sasquatch"
        assert gen_module._strip_cig_size_prefix("") == ""

    def test_blueprint_pool_strips_cig_size_prefix_on_uuid_hit(self, gen_module, tmp_path):
        """CIG 'S0 ' prefix removed from display name before tagging."""
        entity_uuid = "strip-uuid"
        bp_uuid = "strip-bp-uuid"
        pool_uuid = "strip-pool-uuid"

        bp_dir = tmp_path / "bp_strip"
        pool_dir = tmp_path / "pool_strip"

        _write_xml(bp_dir / "mybp.xml", _bp_xml(bp_uuid, entity_uuid))
        _write_xml(pool_dir / "bp_mypool.xml", _pool_xml(pool_uuid, [bp_uuid]))

        entity_names = {entity_uuid: "S0 Helix I"}
        pools, _pool_names = gen_module.build_blueprint_pool_lookup(pool_dir, bp_dir, entity_names)

        assert pools[pool_uuid] == ["Helix I"]

    def test_blueprint_pool_omits_tag_when_dict_unset(self, gen_module, tmp_path):
        """When entity_name_tags not passed (None default), name has no tag suffix."""
        entity_uuid = "notag-uuid"
        bp_uuid = "notag-bp-uuid"
        pool_uuid = "notag-pool-uuid"

        bp_dir = tmp_path / "bp_notag"
        pool_dir = tmp_path / "pool_notag"

        _write_xml(bp_dir / "mybp.xml", _bp_xml(bp_uuid, entity_uuid))
        _write_xml(pool_dir / "bp_mypool.xml", _pool_xml(pool_uuid, [bp_uuid]))

        entity_names = {entity_uuid: "Arbor II"}
        pools, _pool_names = gen_module.build_blueprint_pool_lookup(pool_dir, bp_dir, entity_names)

        assert pools[pool_uuid] == ["Arbor II"]


# ---------------------------------------------------------------------------
# TestPoolRankLabels — T2-C: rank-tier labels from pool filename stems
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPoolRankLabels:
    def test_pool_rank_label_helper(self, gen_module):
        assert gen_module._pool_rank_label("shubinrank0to1") == "Rank 0\u20131"
        assert gen_module._pool_rank_label("shubinrank4") == "Rank 4"
        assert gen_module._pool_rank_label("shubinrank2to3") == "Rank 2\u20133"
        assert gen_module._pool_rank_label("standardregion") == ""
        assert gen_module._pool_rank_label("") == ""
        # case-insensitive
        assert gen_module._pool_rank_label("SHUBIN_RANK1TO2") == "Rank 1\u20132"

    def test_pool_lookup_exposes_stem_as_pool_names(self, gen_module, tmp_path):
        """build_blueprint_pool_lookup second return value maps pool UUID → raw stem."""
        entity_uuid = "rank-entity-uuid"
        bp_uuid = "rank-bp-uuid"
        pool_uuid = "rank-pool-uuid"

        bp_dir = tmp_path / "bp_rank"
        pool_dir = tmp_path / "pool_rank"

        _write_xml(bp_dir / "mybp.xml", _bp_xml(bp_uuid, entity_uuid))
        _write_xml(pool_dir / "bp_rewards_shubinrank4.xml", _pool_xml(pool_uuid, [bp_uuid]))

        entity_names = {entity_uuid: "Bit Breaker"}
        pools, pool_names = gen_module.build_blueprint_pool_lookup(pool_dir, bp_dir, entity_names)

        assert pool_uuid in pool_names
        assert pool_names[pool_uuid] == "shubinrank4"

    def test_scan_groups_items_by_rank_label(self, gen_module, tmp_path):
        """Items from distinct rank pools land in separate label buckets in scan_contract_generators."""
        pool_rank01 = "pool-rank01-uuid"
        pool_rank4 = "pool-rank4-uuid"
        blueprint_pools = {
            pool_rank01: ["Item Alpha"],
            pool_rank4: ["Item Beta"],
        }
        pool_names = {
            pool_rank01: "shubinrank0to1",
            pool_rank4: "shubinrank4",
        }

        cg_dir = tmp_path / "cg_rank"
        _write_xml(
            cg_dir / "contract_rank.xml",
            f"""<?xml version="1.0" encoding="utf-8"?>
<ContractGenerator>
  <ContractGeneratorHandler_List debugName="handler_Stanton">
    <Contract debugName="rank_test_Stanton">
      <ContractStringParam param="Title" value="@rank_title"/>
      <ContractStringParam param="Description" value="@rank_desc"/>
      <BlueprintRewards blueprintPool="{pool_rank01}"/>
      <BlueprintRewards blueprintPool="{pool_rank4}"/>
    </Contract>
  </ContractGeneratorHandler_List>
</ContractGenerator>
""",
        )

        _missions, mission_blueprints, _chance, _items = gen_module.scan_contract_generators(
            cg_dir,
            blueprint_pools=blueprint_pools,
            pool_names=pool_names,
        )

        per_system = mission_blueprints["rank_title"]["Stanton"]
        assert per_system["Rank 0\u20131"] == ["Item Alpha"]
        assert per_system["Rank 4"] == ["Item Beta"]

    def test_scan_falls_back_to_empty_label_when_pool_names_missing(self, gen_module, tmp_path):
        """When pool_names not supplied items land under empty label, not a rank label."""
        pool_uuid = "no-rank-pool-uuid"
        blueprint_pools = {pool_uuid: ["Generic Item"]}

        cg_dir = tmp_path / "cg_norank"
        _write_xml(cg_dir / "contract_norank.xml", _contractgen_xml("norank_title", "Stanton", pool_uuid))

        _missions, mission_blueprints, _chance, _items = gen_module.scan_contract_generators(
            cg_dir, blueprint_pools=blueprint_pools
        )

        per_system = mission_blueprints["norank_title"]["Stanton"]
        assert "" in per_system
        assert per_system[""] == ["Generic Item"]
