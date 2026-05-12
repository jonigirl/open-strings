"""Package an applied global.ini into a shareable zip.

The "Export" toolbar action reads the already-applied global.ini from the
game's localization directory and writes it into a zip suitable for sharing
on Discord, an org website, etc. The zip contains a single global.ini at the
root — recipients drop it into their own
StarCitizen\\<channel>\\data\\Localization\\english\\ directory.

No Open Strings install required on the recipient side.
"""

from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def default_locpack_filename(channel: str, today: datetime | None = None) -> str:
    """Return a sensible default filename for the export dialog.

    Format: ``OpenStrings-LocPack-{channel}-{YYYYMMDD}.zip``. The channel
    is included because loc-files are channel-specific (a PTU export should
    not be applied to LIVE — different stock keys); the date helps the user
    distinguish revisions when iterating.
    """
    when = today or datetime.now()
    return f"OpenStrings-LocPack-{channel}-{when.strftime('%Y%m%d')}.zip"


def write_locpack_zip(source_global_ini: Path, output_zip_path: Path) -> int:
    """Write a zip containing *source_global_ini* as ``global.ini`` at the root.

    Args:
        source_global_ini: Path to the applied ``global.ini`` in the game dir.
        output_zip_path:   Destination zip path chosen by the user.

    Returns:
        Uncompressed size of the source file in bytes (for status feedback).

    Raises:
        FileNotFoundError: if *source_global_ini* does not exist (caller
            should prompt the user to Apply to Game first).
    """
    if not source_global_ini.exists():
        raise FileNotFoundError(f"Applied global.ini not found: {source_global_ini}")

    source_size = source_global_ini.stat().st_size

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # Use the bare filename inside the zip — recipients see "global.ini"
        # at the root, no nested directories.
        zf.write(source_global_ini, arcname="global.ini")

    logger.info(
        "Wrote loc-pack zip: %s (source %d bytes → zip %d bytes)",
        output_zip_path,
        source_size,
        output_zip_path.stat().st_size,
    )
    return source_size
