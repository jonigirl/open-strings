"""Application-level string loading: source orchestration and StringEntry construction.

Sits above the raw parser (ini_parser.parse_ini_file) and below the GUI layer.
Owns the merge → StringEntry pipeline and all AppSettings-driven source loading.
"""

import logging
from pathlib import Path

from src.merger.ini_merger import merge_sources_by_hierarchy
from src.models.string_model import StringEntry
from src.parser.ini_parser import parse_ini_file
from src.utils.perf import timed

logger = logging.getLogger(__name__)


def _build_enhancements_label_category() -> dict[str, str]:
    from src.utils.settings import AppSettings

    result: dict[str, str] = {}
    for category_key, file_labels in AppSettings.ENHANCEMENT_CATEGORY_FILES.items():
        display_label = AppSettings.ENHANCEMENT_LABELS.get(category_key, category_key)
        for label in file_labels:
            result[label] = display_label
    return result


@timed
def load_source_files(
    sources_dict: dict[str, dict[str, str]],
    hierarchy: list[str],
    user_overrides: dict[str, str] | None = None,
    enhancements_key_categories: dict[str, str] | None = None,
) -> list[StringEntry]:
    """Load source files and build StringEntry list using hierarchy merge.

    Merges multiple sources in hierarchy order, then creates StringEntry objects.
    The original_value field contains the merged baseline. The custom_value field
    starts empty and will be populated when user edits in the UI.

    Args:
        sources_dict: Dictionary mapping source names to their key-value dicts.
                     e.g., {"global": {...}, "contracts": {...}, "components": {...}}
        hierarchy: Ordered list of source names to merge.
                  e.g., ["global", "contracts", "components"]
        user_overrides: Optional dict of pre-existing user edits to apply with highest priority.
                       Applied after all sources are merged.

    Returns:
        List of StringEntry objects with merged baseline values and user edits applied.
        custom_value will contain pre-existing edits if user_overrides provided.
    """
    from src.utils.settings import AppSettings

    entries = []

    logger.debug(
        f"Starting merge of {sum(len(d) for d in sources_dict.values())} total keys from {len(sources_dict)} sources"
    )
    logger.debug(f"Hierarchy: {hierarchy}, Sources available: {list(sources_dict.keys())}")

    # Filter hierarchy to only include sources that exist in sources_dict
    filtered_hierarchy = [s for s in hierarchy if s in sources_dict]
    logger.debug(f"Filtered hierarchy: {filtered_hierarchy}")

    filtered_sources = {s: sources_dict[s] for s in filtered_hierarchy}

    # Separate user overrides from the base merge so we can correctly populate
    # custom_value and original_value independently.
    # User data comes either from the explicit user_overrides param or sources_dict["user"].
    effective_user_overrides: dict[str, str] = {}
    if user_overrides:
        effective_user_overrides = dict(user_overrides)
    elif AppSettings.SOURCE_USER in filtered_sources:
        effective_user_overrides = dict(filtered_sources[AppSettings.SOURCE_USER])

    # Build base-only hierarchy / sources (exclude user so original_value is the
    # pre-user-edit baseline, not the already-overridden value).
    base_hierarchy = [s for s in filtered_hierarchy if s != AppSettings.SOURCE_USER]
    base_sources = {k: v for k, v in filtered_sources.items() if k != AppSettings.SOURCE_USER}

    try:
        logger.debug("Calling merge_sources_by_hierarchy (base only, no user)...")
        base_merged = merge_sources_by_hierarchy(base_sources, base_hierarchy, None)
        logger.debug(f"Base merge complete. Result has {len(base_merged)} keys")
    except Exception as e:
        logger.exception(f"Error during merge: {e}")
        raise

    # Track which base source each key came from (for status of non-user entries)
    logger.debug("Tracking source origin for each key...")
    source_origin: dict[str, str] = {}
    for source_name in base_hierarchy:
        source_data = base_sources[source_name]
        for key in source_data.keys():
            source_origin[key] = source_name
    logger.debug(f"Source origin tracking complete. {len(source_origin)} keys tracked")

    # Build the full key universe: all base keys + user-only "New" keys
    all_keys = set(base_merged.keys()) | set(effective_user_overrides.keys())

    # Create StringEntry for each key
    logger.debug("Creating StringEntry objects...")
    base_source = base_hierarchy[0] if base_hierarchy else "global"
    entry_count = 0
    for key in all_keys:
        # Skip abbreviated ship name entries (e.g. vehicle_Name*_short, vehicle_name*_short,P)
        if key.lower().startswith("vehicle_name") and "_short" in key:
            continue

        entry_count += 1
        if entry_count % 10000 == 0:
            logger.debug(f"Processing entry {entry_count} of ~{len(all_keys)}...")

        original_value = base_merged.get(key, "")
        custom_value = effective_user_overrides.get(key, "")

        # Determine status
        if key not in base_merged:
            # Only in user overrides — user added a brand-new key
            status = "New"
        elif custom_value:
            # User has an override for this key
            status = "Modified"
        else:
            # No user override — use source-origin-based status
            source = source_origin.get(key, base_source)
            status = _determine_status_from_source(source, base_source)

        source = source_origin.get(key, "user" if key not in base_merged else base_source)

        # Determine category: source-based override first, then key-prefix fallback
        if source == "contracts":
            category = "Missions"
        elif "journal" in key.lower():
            category = "Journal"
        elif enhancements_key_categories and key in enhancements_key_categories:
            category = enhancements_key_categories[key]
        else:
            category = StringEntry.extract_category(key)

        entry = StringEntry(
            key=key,
            source_file=source,
            category=category,
            original_value=original_value,
            custom_value=custom_value,
            status=status,
        )
        entries.append(entry)

    logger.info(f"Created {len(entries)} StringEntry objects successfully")
    return entries


@timed
def load_sources_from_settings() -> tuple[dict[str, dict[str, str]], list[str], dict[str, str]]:
    """Load all sources from application settings.

    For remote URLs, loads from cached local files if available.
    For local paths, loads directly.
    Remote sources are downloaded asynchronously by the update checker, not here.

    Returns:
        Tuple of (sources_dict, hierarchy, enhancements_key_categories) where:
        - sources_dict: Dict mapping source names to key-value dicts
        - hierarchy: List of source names in merge order
        - enhancements_key_categories: Dict mapping enhancement key → category name
    """
    from src.utils.settings import AppSettings

    sources_dict: dict[str, dict[str, str]] = {}
    hierarchy = AppSettings.get_merge_hierarchy()

    # Map source names to their cached file names in Documents cache
    cache_mapping = {
        AppSettings.SOURCE_GLOBAL: "base.ini",
    }

    cache_dir = AppSettings.get_cache_dir()

    # Load each configured source
    logger.info(f"Loading sources from settings. Available sources: {AppSettings.AVAILABLE_SOURCES}")
    for source_name in AppSettings.AVAILABLE_SOURCES:
        if not AppSettings.is_source_enabled(source_name):
            logger.debug(f"Source {source_name} is disabled")
            continue

        source_path = AppSettings.get_source_path(source_name)
        if not source_path:
            logger.debug(f"Source {source_name} has no path configured")
            continue

        logger.debug(f"Processing source {source_name}: {source_path}")

        try:
            # Handle URLs vs local files
            if source_path.startswith(("http://", "https://")):
                # For remote sources, load from cached local file in AppData (must exist)
                if source_name in cache_mapping:
                    cache_file = cache_dir / cache_mapping[source_name]
                    logger.debug(f"Looking for cache file: {cache_file}")

                    if cache_file.exists():
                        logger.debug(f"Cache file found, parsing {source_name}...")
                        source_data = parse_ini_file(cache_file)
                        if source_data:
                            sources_dict[source_name] = source_data
                            logger.info(f"Loaded {len(source_data)} entries from {source_name}")
                        else:
                            logger.warning(f"Parsed {source_name} but got empty result")
                    else:
                        logger.error(f"Remote source {source_name} requires download. Cache not found: {cache_file}")
                        raise FileNotFoundError(
                            f"Source {source_name} cache not found. Run auto-update to download: {cache_file}"
                        )
                continue

            # Local file path
            logger.debug(f"Loading local file {source_path}...")
            local_file = Path(source_path)

            # User source can be empty on first run
            if source_name == AppSettings.SOURCE_USER:
                if local_file.exists():
                    source_data = parse_ini_file(source_path)
                    if source_data:
                        sources_dict[source_name] = source_data
                        logger.info(f"Loaded {len(source_data)} entries from {source_name}")
                    else:
                        logger.debug(f"User overrides file is empty: {source_path}")
                else:
                    logger.debug(f"No user overrides yet: {source_path}")
                continue

            # Other local sources must exist
            if not local_file.exists():
                logger.error(f"Local file not found: {source_path}")
                raise FileNotFoundError(f"Source {source_name} file not found: {source_path}")

            source_data = parse_ini_file(source_path)
            if source_data:
                sources_dict[source_name] = source_data
                logger.info(f"Loaded {len(source_data)} entries from {source_name}")
        except Exception as e:
            logger.exception(f"Failed to load source {source_name} from {source_path}: {e}")

    # ── Enhancements ────────────────────────────────────────────────────────
    enhancements_key_categories: dict[str, str] = {}
    enabled_categories = AppSettings.get_enabled_enhancement_categories()
    if enabled_categories:
        enhancements_label_category = _build_enhancements_label_category()
        enhancements_combined: dict[str, str] = {}
        for label, filename in AppSettings.ENHANCEMENTS_FILES.items():
            if label not in enabled_categories:
                continue
            enhancements_file = cache_dir / filename
            if enhancements_file.exists():
                data = parse_ini_file(enhancements_file)
                category = enhancements_label_category.get(label)
                if category:
                    for key in data:
                        enhancements_key_categories[key] = category
                enhancements_combined.update(data)
                logger.info(f"Loaded {len(data)} enhancement entries from {filename}")
            else:
                logger.debug(f"Enhancements file not found (skipping): {enhancements_file}")

        if enhancements_combined:
            sources_dict["enhancements"] = enhancements_combined
            logger.info(f"Enhancements: {len(enhancements_combined)} total entries loaded")
            # Insert "enhancements" just before "user" in the hierarchy (or at end if no user)
            if AppSettings.SOURCE_USER in hierarchy:
                idx = hierarchy.index(AppSettings.SOURCE_USER)
                hierarchy = hierarchy[:idx] + ["enhancements"] + hierarchy[idx:]
            else:
                hierarchy = hierarchy + ["enhancements"]

    logger.info(f"load_sources_from_settings complete. Loaded sources: {list(sources_dict.keys())}")
    return sources_dict, hierarchy, enhancements_key_categories


def _determine_status_from_source(source_name: str, base_source: str) -> str:
    """Determine status based on which source provided the value.

    Args:
        source_name: Name of the source that provided this value
        base_source: Name of the base source (usually 'global')

    Returns:
        One of:
        - 'Modified':   user explicitly customized this entry, or overridden
                        by any other higher-priority non-enhancements source
        - 'Enhanced':   generated by the enhancements pipeline
        - 'Unmodified': stock base.ini value, unchanged
    """
    if source_name == "user":
        return "Modified"
    if source_name == "enhancements":
        return "Enhanced"
    if source_name == base_source:
        return "Unmodified"
    return "Modified"
