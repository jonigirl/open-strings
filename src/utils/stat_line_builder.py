from __future__ import annotations

from typing import Any

from src.utils.formatting import fmt as _fmt


class StatLineBuilder:
    """Fluent builder for stat lines in enhancement formatters.

    Eliminates repetitive line-building code across formatters.
    Each method returns self to enable chaining.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, label: str, value: Any, unit: str = "", decimals: int = 0) -> StatLineBuilder:
        """Add single stat line if value is non-None/non-zero.

        Args:
            label: Stat label (e.g. "Max Speed")
            value: Numeric value (skipped if None)
            unit: Optional unit suffix (e.g. "m/s", "kW")
            decimals: Decimal places for formatting

        Returns:
            self for chaining
        """
        if value is not None:
            self.lines.append(f"{label}: {_fmt(value, unit, decimals)}")
        return self

    def add_multi(self, label: str, **kwargs: Any) -> StatLineBuilder:
        """Add multi-part stat line with sub-labels.

        Example:
            builder.add_multi("Damage", P=100, E=50, D=25)
            # Produces: "Damage: P 100  |  E 50  |  D 25"

        Args:
            label: Main label
            **kwargs: Sub-label=value pairs (None values skipped)

        Returns:
            self for chaining
        """
        parts = [f"{k} {_fmt(v)}" for k, v in kwargs.items() if v is not None]
        if parts:
            self.lines.append(f"{label}: " + "  |  ".join(parts))
        return self

    def build(self) -> str:
        """Build final stat block with escaped newlines.

        Returns:
            Stat lines joined by \\n
        """
        return "\\n".join(self.lines)
