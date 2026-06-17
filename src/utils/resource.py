"""Resource path resolution for dev and PyInstaller frozen builds."""

import os
import sys
from pathlib import Path


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        # If not running as PyInstaller bundle, use the project root
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    return os.path.join(base_path, relative_path)


def _resolve_patches_dir() -> Path:
    """Return the path to the bundled DataForge patches directory."""
    return Path(get_resource_path("patches"))
