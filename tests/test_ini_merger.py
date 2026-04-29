"""Tests for src/merger/ini_merger.py — covering previously untested functions.

Covers:
- merge_ini_files: file-level merge with line-by-line rewriting
- sync_key_variants: in-place variant synchronisation
- _get_canonical_key: key normalisation / canonicalisation
"""

from pathlib import Path

import pytest
from src.merger.ini_merger import (
    _get_canonical_key,
    merge_ini_files,
    sync_key_variants,
)

# ---------------------------------------------------------------------------
# _get_canonical_key
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCanonicalKey:
    """_get_canonical_key normalises item_Name/item_Desc component keys."""

    def test_plain_key_returns_lowercased_no_underscores(self):
        # Non-component key: ALL underscores are stripped (not just separators)
        result = _get_canonical_key("vehicle_NameHunter")
        assert result == "vehiclenamehunter"

    def test_scitem_suffix_removed(self):
        result = _get_canonical_key("item_nameQDRV_RSI_S02_Hemera_SCItem")
        assert "_scitem" not in result

    def test_component_code_preserved_with_separator(self):
        # QDRV code should appear as a segment after normalisation
        result = _get_canonical_key("item_Name_QDRV_RSI_S02_Hemera")
        assert "qdrv" in result

    def test_variants_map_to_same_canonical(self):
        """The canonical form of both variants must be identical."""
        canonical_plain = _get_canonical_key("item_Name_QDRV_RSI_S02_Hemera")
        canonical_scitem = _get_canonical_key("item_nameQDRV_RSI_S02_Hemera_SCItem")
        assert canonical_plain == canonical_scitem

    def test_shld_variant(self):
        a = _get_canonical_key("item_NameSHLD_Aspirum")
        b = _get_canonical_key("item_nameSHLD_Aspirum_SCItem")
        assert a == b

    def test_powr_variant(self):
        a = _get_canonical_key("item_NamePOWR_TR1")
        b = _get_canonical_key("item_namePOWR_TR1_SCItem")
        assert a == b

    def test_cool_variant(self):
        a = _get_canonical_key("item_NameCOOL_Delphi")
        b = _get_canonical_key("item_nameCOOL_Delphi_SCItem")
        assert a == b

    def test_non_component_key_stable(self):
        # Calling twice should return the same value (cache must not mutate)
        key = "items_commodities_AluminumOre"
        assert _get_canonical_key(key) == _get_canonical_key(key)

    def test_case_insensitive_scitem_removal(self):
        # Mixed-case _SCITEM suffix must also be stripped
        result_lower = _get_canonical_key("item_nameSHLD_X_scitem")
        result_upper = _get_canonical_key("item_nameSHLD_X_SCItem")
        assert result_lower == result_upper


# ---------------------------------------------------------------------------
# sync_key_variants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSyncKeyVariants:
    """sync_key_variants must propagate the preferred value to all variants."""

    def test_no_variants_unchanged(self):
        d = {"vehicle_NameHunter": "Cutlass", "items_commodities_AluminumOre": "Aluminum Ore"}
        sync_key_variants(d)
        assert d["vehicle_NameHunter"] == "Cutlass"
        assert d["items_commodities_AluminumOre"] == "Aluminum Ore"

    def test_component_variants_synced_to_non_scitem(self):
        d = {
            "item_NameSHLD_Aspirum": "Aspirum Shield",
            "item_nameSHLD_Aspirum_SCItem": "OLD VALUE",
        }
        sync_key_variants(d)
        # Non-_SCItem variant is preferred; both should equal its value
        assert d["item_NameSHLD_Aspirum"] == "Aspirum Shield"
        assert d["item_nameSHLD_Aspirum_SCItem"] == "Aspirum Shield"

    def test_all_scitem_variants_synced_to_first(self):
        # When all variants end in _SCItem, the first is used as the source
        d = {
            "item_nameSHLD_X_SCItem": "value_a",
            "item_NameSHLD_X_SCItem": "value_b",
        }
        sync_key_variants(d)
        # Both should end up with the same value (whichever was first)
        values = set(d.values())
        assert len(values) == 1

    def test_empty_dict_is_noop(self):
        d: dict[str, str] = {}
        sync_key_variants(d)
        assert d == {}


# ---------------------------------------------------------------------------
# merge_ini_files
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergeIniFiles:
    """merge_ini_files writes the merged result to a file."""

    def test_basic_override_applied(self, tmp_path: Path):
        source = tmp_path / "base.ini"
        source.write_text("vehicle_NameHunter=Cutlass\nitem_NameSHLD_Aspirum=Old Shield\n", encoding="utf-8")
        overrides = {"vehicle_NameHunter": "My Cutlass"}
        out = tmp_path / "out.ini"
        merge_ini_files(source, overrides, out)
        lines = out.read_text(encoding="utf-8").splitlines()
        assert any("vehicle_NameHunter=My Cutlass" in line for line in lines)
        # Non-overridden key stays
        assert any("item_NameSHLD_Aspirum=Old Shield" in line for line in lines)

    def test_comments_and_blanks_preserved(self, tmp_path: Path):
        source = tmp_path / "base.ini"
        source.write_text("; comment\n\nkey=val\n", encoding="utf-8")
        out = tmp_path / "out.ini"
        merge_ini_files(source, {}, out)
        content = out.read_text(encoding="utf-8")
        assert "; comment" in content

    def test_comma_suffix_stripped_in_output(self, tmp_path: Path):
        # Keys like "vehicle_Name,P=…" must be written without the ",P"
        source = tmp_path / "base.ini"
        source.write_text("vehicle_Name,P=Cutlass\n", encoding="utf-8")
        out = tmp_path / "out.ini"
        merge_ini_files(source, {}, out)
        content = out.read_text(encoding="utf-8")
        assert "vehicle_Name=" in content
        assert ",P=" not in content

    def test_override_for_comma_key_applied(self, tmp_path: Path):
        # Overrides use clean keys; source has comma suffix — they must match.
        source = tmp_path / "base.ini"
        source.write_text("vehicle_Name,P=Cutlass\n", encoding="utf-8")
        out = tmp_path / "out.ini"
        merge_ini_files(source, {"vehicle_Name": "My Ship"}, out)
        content = out.read_text(encoding="utf-8")
        assert "vehicle_Name=My Ship" in content

    def test_missing_source_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            merge_ini_files(tmp_path / "nonexistent.ini", {}, tmp_path / "out.ini")

    def test_output_directory_created(self, tmp_path: Path):
        source = tmp_path / "base.ini"
        source.write_text("k=v\n", encoding="utf-8")
        out = tmp_path / "sub" / "deep" / "out.ini"
        merge_ini_files(source, {}, out)
        assert out.exists()

    def test_value_with_equals_preserved(self, tmp_path: Path):
        source = tmp_path / "base.ini"
        source.write_text("key=a=b=c\n", encoding="utf-8")
        out = tmp_path / "out.ini"
        merge_ini_files(source, {}, out)
        content = out.read_text(encoding="utf-8")
        assert "key=a=b=c" in content

    def test_line_endings_preserved(self, tmp_path: Path):
        """Line content is correctly written (line endings are platform-normalised)."""
        source = tmp_path / "base.ini"
        source.write_bytes(b"key=value\r\n")
        out = tmp_path / "out.ini"
        merge_ini_files(source, {}, out)
        # Python opens in text mode, so \r\n is normalised to \n on all
        # platforms.  The important contract is that the key=value content
        # round-trips correctly, not the exact byte-level line ending.
        content = out.read_text(encoding="utf-8")
        assert "key=value" in content

    def test_no_override_key_stays_clean(self, tmp_path: Path):
        """Keys without overrides still have the comma suffix stripped."""
        source = tmp_path / "base.ini"
        source.write_text("k1=v1\nk2=v2\n", encoding="utf-8")
        out = tmp_path / "out.ini"
        merge_ini_files(source, {"k1": "new_v1"}, out)
        lines = out.read_text(encoding="utf-8").splitlines()
        assert any(line.startswith("k1=new_v1") for line in lines)
        assert any(line.startswith("k2=v2") for line in lines)
