"""Application-level domain constants — channel names, RSI paths, enhancement mappings.

These are pure data with no dependencies on settings storage, Qt, or I/O.
AppSettings re-exports them as class attributes so all existing callers work
unchanged.  Code that only needs the data (e.g. string_loader, workers) can
import directly from this module instead of pulling in the full AppSettings
class.
"""

# ── Star Citizen channel names ────────────────────────────────────────────────

CHANNEL_LIVE = "LIVE"
CHANNEL_PTU = "PTU"
CHANNEL_EPTU = "EPTU"
CHANNEL_HOTFIX = "HOTFIX"
CHANNEL_TECH_PREVIEW = "TECH-PREVIEW"

AVAILABLE_CHANNELS: tuple[str, ...] = (
    CHANNEL_LIVE,
    CHANNEL_PTU,
    CHANNEL_EPTU,
    CHANNEL_HOTFIX,
    CHANNEL_TECH_PREVIEW,
)
DEFAULT_CHANNEL = CHANNEL_LIVE

# ── Common RSI install roots (Windows) ───────────────────────────────────────
# Candidates tried in order by auto-detection and ensure_default_settings.

_RSI_DEFAULT_ROOTS: tuple[str, ...] = (
    r"C:\Program Files\Roberts Space Industries\StarCitizen",
    r"C:\Program Files (x86)\Roberts Space Industries\StarCitizen",
)

# ── Enhancement file mappings ─────────────────────────────────────────────────
# These four dicts grow as new enhancement types are added; keeping them here
# separates Star Citizen domain data from settings-storage infrastructure.

# Maps logical enhancement keys to the INI filenames written by generate_enhancements_ini.py.
ENHANCEMENTS_FILES: dict[str, str] = {
    "ship_descs": "ships_desc_enhancements.ini",
    "component_descs": "components_desc_enhancements.ini",
    "ship_weapon_descs": "ship_weapons_desc_enhancements.ini",
    "fps_weapon_descs": "fps_weapons_desc_enhancements.ini",
    "fps_attachment_descs": "fps_attachments_enhancements.ini",
    "ship_fuel_descs": "ship_fuel_enhancements.ini",
    "countermeasure_descs": "countermeasure_enhancements.ini",
    "lifesupport_descs": "lifesupport_enhancements.ini",
    "mission_rewards": "mission_rewards_enhancements.ini",
    "commodity_crafting": "commodity_crafting_enhancements.ini",
    "journal": "journal_enhancements.ini",
    "missile_enhancements": "missile_enhancements.ini",
}

# Maps checkbox/category keys to user-facing labels shown in the enhancements UI.
ENHANCEMENT_LABELS: dict[str, str] = {
    "ships": "Ships",
    "ship_items": "Ship Items",
    "gear": "Gear",
    "missions": "Missions",
    "commodities": "Commodities",
    "journal": "Journal",
}

# Maps each checkbox key to the enhancement file keys it controls.
ENHANCEMENT_CATEGORY_FILES: dict[str, list[str]] = {
    "ships": ["ship_descs"],
    "ship_items": [
        "component_descs",
        "ship_weapon_descs",
        "missile_enhancements",
        "ship_fuel_descs",
        "countermeasure_descs",
        "lifesupport_descs",
    ],
    "gear": ["fps_weapon_descs", "fps_attachment_descs"],
    "missions": ["mission_rewards"],
    "commodities": ["commodity_crafting"],
    "journal": ["journal"],
}

# Maps dataforge_diff.CATEGORY_SUBTREES keys to generate_enhancements_ini.py file keys.
# Used by EnhancementsGeneratorWorker to translate dirty_categories() output into the
# generator's internal vocabulary.
DIFF_CATEGORY_TO_GENERATOR_KEYS: dict[str, list[str]] = {
    "ships": ["ship_descs"],
    "components": ["component_descs"],
    "ship_weapons": [
        "ship_weapon_descs",
        "missile_enhancements",
        "ship_fuel_descs",
        "countermeasure_descs",
        "lifesupport_descs",
    ],
    "fps_weapons": ["fps_weapon_descs", "fps_attachment_descs"],
    "missions": ["mission_rewards"],
    "commodities": ["commodity_crafting"],
    "journal": ["journal"],
}
