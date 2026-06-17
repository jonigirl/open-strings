from dataclasses import dataclass

from src.utils.category_classifier import _extract_category_impl


@dataclass
class StringEntry:
    """Represents a localization string entry."""

    key: str
    source_file: str  # "global" or "vehicles"
    category: str = ""  # Extracted from key prefix
    original_value: str = ""  # From merged sources (base file + others)
    custom_value: str = ""  # From target_strings.ini (or empty)
    status: str = ""  # "Modified" | "Enhanced" | "Unmodified" | "New"

    def __post_init__(self) -> None:
        # Older call sites sometimes omitted category/status and relied on the
        # model to infer them; keep that compatibility without a custom __init__.
        if not self.category:
            self.category = self.extract_category(self.key)
        if not self.status:
            self.status = self._determine_status(self.original_value, self.custom_value)

    @property
    def is_modified(self) -> bool:
        """Check if custom value differs from original."""
        return bool(self.custom_value and self.custom_value != self.original_value)

    @staticmethod
    def _determine_status(original_value: str, custom_value: str) -> str:
        """Infer status for legacy call sites that omit it."""
        if not custom_value or custom_value == original_value:
            return "Unmodified"
        return "Modified"

    @staticmethod
    def extract_category(key: str) -> str:
        """Extract category from key prefix.

        Thin wrapper over the module-level memoized :func:`_extract_category_impl`
        so call sites keep their existing ``StringEntry.extract_category(key)``
        shape while benefiting from module-level constants + LRU caching.

        Rules:
        - Keys starting with ``vehicle_Name`` / ``vehicle_Desc`` → Ships
        - ``item_Name(SHLD|POWR|COOL|QDRV|JUMP|MISL|GMISL|BOMB)`` → Ship Items
        - Mission-related keys (contracts, shubin, blackbox, hockrow, …) → Missions
        - Everything else → Other
        """
        return _extract_category_impl(key)
