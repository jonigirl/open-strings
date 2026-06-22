"""
formatting.py
─────────────
Shared formatting utilities for enhancement text generation.
"""

from __future__ import annotations

# Items with this overheat temp have no real overheat stat
OVERHEAT_PLACEHOLDER = 450_000

# Null UUID constant for DataForge entity references
NULL_UUID = "00000000-0000-0000-0000-000000000000"


def fmt(value, unit: str = "", decimals: int = 0) -> str:
    """Format a numeric value with optional unit and decimal places.

    Args:
        value: Numeric value to format (or None)
        unit: Optional unit string to append (e.g. " HP/s")
        decimals: Number of decimal places (0 for integer formatting)

    Returns:
        Formatted string with thousands separators and unit, or "?" if value is None
    """
    if value is None:
        return "?"
    try:
        v = float(value)
        if decimals:
            return f"{v:,.{decimals}f}{unit}"
        return f"{int(round(v)):,}{unit}"
    except (TypeError, ValueError):
        return str(value)
