"""Manages Star Citizen user.cfg file for language and other settings."""

import logging
import re
from pathlib import Path

from src.utils.settings import AppSettings

logger = logging.getLogger(__name__)

_LANGUAGE_SETTING = "g_language = english"

# Match any ``g_language`` assignment regardless of spacing, case, or value.
# SC's user.cfg parser is lenient: ``g_language=english``, ``G_Language =
# English``, and ``g_language = "english"`` are all valid. The previous
# exact-string check missed those and appended a duplicate line on every
# apply, which is the bug this regex fixes.
_LANGUAGE_KEY_RE = re.compile(r"^\s*g_language\s*=", re.IGNORECASE)
_LANGUAGE_KV_RE = re.compile(
    r'^\s*g_language\s*=\s*"?([^";\r\n]+?)"?\s*(?:[;#].*)?$',
    re.IGNORECASE,
)


def ensure_user_cfg_language() -> bool:
    """Ensure Star Citizen's user.cfg has g_language = english setting.

    Writes to the **active channel's** ``user.cfg`` — whichever of
    LIVE/PTU/EPTU/HOTFIX/TECH-PREVIEW is currently selected. Creates the
    file if absent, or adds the language line if the key is entirely
    missing. If ``g_language`` is already set — to any value, in any
    spacing/casing — the file is left untouched; we don't silently
    overwrite a user's intentional choice (e.g. a non-English locale).
    Non-English values get an INFO log so the user has a breadcrumb if
    their localization customizations aren't showing up.

    Returns:
        True if successful, False if the channel's install dir isn't
        accessible (channel not installed, path misconfigured, etc.).
    """
    channel_path = AppSettings.get_game_install_path()
    if not channel_path:
        logger.warning("Game install path not configured — skipping user.cfg setup")
        return False

    channel_dir = Path(channel_path)
    if not channel_dir.exists():
        logger.warning(
            f"{AppSettings.get_active_channel()} directory not found at {channel_dir} — skipping user.cfg setup"
        )
        return False

    user_cfg_path = channel_dir / "user.cfg"

    try:
        if not user_cfg_path.exists():
            logger.info(f"Creating user.cfg at {user_cfg_path}")
            user_cfg_path.write_text(_LANGUAGE_SETTING + "\n", encoding="utf-8")
            logger.info(f"Created user.cfg with '{_LANGUAGE_SETTING}'")
            return True

        content = user_cfg_path.read_text(encoding="utf-8")
        existing_value: str | None = None
        for line in content.splitlines():
            if _LANGUAGE_KEY_RE.match(line):
                match = _LANGUAGE_KV_RE.match(line)
                existing_value = match.group(1).strip() if match else ""
                break

        if existing_value is not None:
            if existing_value.lower() != "english":
                logger.info(
                    f"user.cfg already sets g_language to {existing_value!r} — "
                    f"leaving as-is. Open Strings' English customizations won't "
                    f"show in-game unless this is set to 'english'."
                )
            else:
                logger.info("user.cfg already has g_language=english; not modifying")
            return True

        logger.info(f"Adding language setting to {user_cfg_path}")
        lines = content.splitlines()
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(_LANGUAGE_SETTING)
        user_cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"Added '{_LANGUAGE_SETTING}' to user.cfg")
        return True
    except Exception as e:
        logger.exception(f"Failed to manage user.cfg at {user_cfg_path}: {e}")
        return False
