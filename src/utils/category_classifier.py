"""Category classification for Star Citizen localization key names.

Extracted from string_model so the lookup tables and classifier function are
independently testable without importing the data model.
"""

import re
from functools import cache

# ── Module-level lookup tables ─────────────────────────────────────────────────
# All of these used to be re-created on every call. At 87k entries loaded and
# _extract_category_impl() being hit twice per entry (filter pass in ini_parser
# + StringEntry assignment in load_source_files), that was ~174k list/set
# rebuilds and ~174k regex compilations per source-load pass. Hoisting them
# to module scope plus the @cache below dropped that whole block of work.

_FPS_WEAPON_WORDS = (
    "_rifle_",
    "_pistol_",
    "_smg_",
    "_shotgun_",
    "_sniper_",
    "_launcher_",
    "_lmg_",
    "_hmg_",
    "_knife_",
    "_multi_",
)
_ARMOR_GEAR_WORDS = (
    "armor",
    "helmet",
    "suit",
    "vest",
    "glasses",
    "_optics_",
    "_barrel_",
)

# Ship-component type codes. Pre-expanded to all four valid
# (item_Name|item_Desc) × (with|without underscore) forms at import time, so
# the hot path is a single startswith(tuple) call — CPython implements that
# in C and short-circuits on first match.
_COMPONENT_CODES = ("shld", "powr", "cool", "qdrv", "jump", "misl", "gmisl", "bomb")
_COMPONENT_PREFIXES = tuple(
    f"item_{field}{sep}{comp}_" for comp in _COMPONENT_CODES for field in ("name", "desc") for sep in ("", "_")
)

# Ship-weapon size designator (_S1, _S02, _XL, _XL-2, _XXL, _L-3, …).
_SHIP_WEAPON_SIZE_RE = re.compile(r"_S\d+|_X{1,2}L(-\d+)?|_[LMS]-\d+", re.IGNORECASE)

# Mission-source prefixes. Turned into a sorted tuple so
# ``key_lower.startswith(_MISSION_PREFIXES)`` can run the C-level tuple
# implementation of startswith — orders of magnitude faster than an
# ``any(key_lower.startswith(p) for p in prefixes)`` Python loop over a
# ~140-element set. Prefixes derived from mission_rewards_enhancements.ini,
# contracts.ini, and DataForge pu_missions entities. Comparison is
# case-insensitive (we lower the key first). Bare prefixes (no trailing _)
# are preferred where safe, to catch variant spellings (bitzeros vs bitzeroes).
_MISSION_PREFIXES = (
    "adagio_",
    "assassin",
    "basesweep_",
    "bbt_",
    "bhg_",
    "bitzero",
    "blackbox",
    "blacjac",
    "blockaderunner",
    "bounty_",
    "cdf_",
    "cfp",
    "civilian_",
    "claimsweep_",
    "cleanair_",
    "clovis_",
    "combatassist_",
    "commarray",
    "confirmkill_",
    "constantine_",
    "contract",
    "covalex",
    "criminal_",
    "crusader_",
    "crus_",
    "dataheis",
    "deadsaints_",
    "deploypiggyback_",
    "deployprobe_",
    "destroyblade_",
    "destroydebris_",
    "destroyitem_",
    "destroyprobe",
    "destroystash_",
    "distraction",
    "dusters_",
    "eckhart",
    "ecn_",
    "escort_",
    "fffinale_",
    "firesale_",
    "forcedepletion",
    "foxwell_",
    "fps_bounty",
    "ftl_",
    "genlocal_",
    "gobling_",
    "groupbounty_",
    "hack_",
    "haulcargo_",
    "hdactivist_",
    "headhunters_",
    "hexpenetrator_",
    "hh_",
    "highpoint_",
    "hockcrow_",
    "hockrow_",
    "hurston_",
    "intersec_",
    "jt_",
    "kaboos_",
    "kareahsweep_",
    "killship_",
    "lingfamily_",
    "localdelivery_",
    "locationrush_",
    "me_blackbox",
    "me_bounty",
    "me_planetcollect",
    "meet_",
    "mg_",
    "mgclovus_",
    "miningclaim",
    "mission",
    "mtps_",
    "murderspree_",
    "ninetails_",
    "northrock_",
    "ntlockdown_",
    "outpost_repair",
    "outlawsweep_",
    "p_showdown",
    "p_protect",
    "planetcollect_",
    "preventdata_",
    "prisonerbreak_",
    "protlife_",
    "rain_",
    "recovery_",
    "recoverstash_",
    "recoverstolen_",
    "redwind_",
    "repairoxygenkiosk_",
    "retakelocation_",
    "retrieveconsignment_",
    "retrievedatapad_",
    "roughready_",
    "ruto_",
    "scramblerace_",
    "searchbody",
    "searchcrew_",
    "sectorsweep_",
    "securitypatrol_",
    "servicebeacon_",
    "shubin_",
    "singleidrisfight_",
    "spacecargo_",
    "spacecollect",
    "spacesteal_",
    "stealevidence_",
    "stealitem_",
    "tarpits_",
    "test_title_",
    "thecollector_",
    "timesensitive_",
    "tutorial",
    "udm_",
    "uwc_",
    "vaughn_",
    "vendingmachine_",
    "wantedlevel",
    "wstr_",
    "xenothreat_",
)


@cache
def _extract_category_impl(key: str) -> str:
    """Memoized category classifier for Star Citizen localization key names.

    The source-load pipeline calls extract_category twice per entry (once
    in ini_parser's filter pass, once assigning StringEntry.category) — the
    second call is guaranteed to hit the cache. Cache is unbounded because
    the universe of keys is bounded (~87k base + ~4k enhancements), and a
    stale cache entry is harmless since the mapping is pure.
    """
    if not key:
        return "Other"

    key_lower = key.lower()

    # Ship/vehicle names and descriptions: vehicle_NameANVL_Carrack,
    # vehicle_DescANVL_Carrack → Ships
    if key_lower.startswith(("vehicle_name", "vehicle_desc")):
        return "Ships"

    # Wikelo ship mods (TheCollector_ShipMod_*_VehicleName, _VehicleDesc,
    # _VehicleNameShort). Checked before mission-prefix fallthrough, which
    # would otherwise route TheCollector_* into "Missions".
    if key_lower.endswith(("_vehiclename", "_vehicledesc", "_vehiclenameshort")):
        return "Ships"

    if key_lower.startswith(("item_name", "item_desc")):
        # Turrets are ship items despite the item_Name_/item_Desc_ prefix.
        if key_lower.startswith(("item_name_turret", "item_desc_turret")):
            return "Ship Items"

        # Ship component type codes (SHLD/POWR/COOL/QDRV/JUMP/MISL/GMISL/BOMB)
        # with or without a separating underscore.
        if key_lower.startswith(_COMPONENT_PREFIXES):
            return "Ship Items"

        # FPS weapon tokens (catches GMNI/KSAR uppercase counterexamples).
        if any(w in key_lower for w in _FPS_WEAPON_WORDS):
            return "Gear"

        # FPS armor / equipment / accessories.
        if any(w in key_lower for w in _ARMOR_GEAR_WORDS):
            return "Gear"

        # Case-based classification: the segment after item_Name / item_Desc
        # reveals domain. Uppercase = ship items (item_NameBEHR_*,
        # item_DescAEGS_*), lowercase = FPS gear (item_Namebehr_*,
        # item_Descgmni_*).
        after = key[9:]  # both "item_Name" and "item_Desc" are 9 chars
        if after and not after.startswith("_"):
            return "Ship Items" if after[0].isupper() else "Gear"

        # item_Name_ keys: size designator for ship weapons (_S1, _S02, _XL, …).
        if _SHIP_WEAPON_SIZE_RE.search(key):
            return "Ship Items"

        # Remaining item_Name_ / item_Desc_ keys are FPS gear.
        if key_lower.startswith(("item_name_", "item_desc_")):
            return "Gear"

    if key_lower.startswith("item_mining_gadget_"):
        return "Gear"
    if key_lower.startswith("item_mining_"):
        return "Ship Items"
    if key_lower.startswith("items_commodities_"):
        return "Commodities"
    if "journal" in key_lower:
        return "Journal"
    if key_lower.startswith(_MISSION_PREFIXES):
        return "Missions"

    return "Other"
