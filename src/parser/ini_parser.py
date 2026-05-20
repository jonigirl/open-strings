"""INI file parser for localization strings."""

import logging
from pathlib import Path

from src.utils.perf import timed

logger = logging.getLogger(__name__)


@timed
def parse_ini_file(path: str | Path) -> dict[str, str]:
    """Parse INI file line-by-line, preserving efficiency.

    Strips any comma-based metadata suffix from keys (e.g., "key,P" → "key").
    This ensures keys from different sources (especially downloaded base.ini) are
    normalized and don't get written with unwanted suffixes.

    Args:
        path: Path to INI file

    Returns:
        Dictionary of key-value pairs
    """
    result: dict[str, str] = {}
    path = Path(path)

    if not path.exists():
        return result

    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                # strip() once — removes newlines and any surrounding whitespace.
                # Avoids the previous pattern of rstrip("\n\r") + two strip() calls.
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith(";"):
                    continue

                # Split on first '=' only
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if key:
                    # Strip comma-based metadata suffix (e.g., "key,P" → "key").
                    # partition() avoids allocating a list; left side is always the key.
                    clean_key = key.partition(",")[0].strip()
                    if clean_key:
                        result[clean_key] = value
    except Exception:
        logger.exception("Error parsing INI file %s", path)

    return result


@timed
def load_overrides(target_path: str | Path) -> dict[str, str]:
    """Load override strings from target_strings.ini.

    Args:
        target_path: Path to target_strings.ini

    Returns:
        Dictionary of overrides
    """
    return parse_ini_file(target_path)
