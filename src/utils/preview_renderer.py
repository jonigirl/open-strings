"""Preview-pane rendering and frontend version stamping utilities.

Extracted from main_window so these pure functions can be tested
without triggering Qt widget construction.
"""

import html as _html_mod
import re as _re_mod

from src.utils.version import get_version

# Token translation patterns — turns the raw loc-string format the game
# reads into styled HTML that mirrors the in-game feel. Patterns:
#   \n              → line break
#   <EM3>X</EM3>    → block-level heading (section dividers)
#   <EM4>X</EM4>    → inline emphasis (stats / tag values)
#   ~mission(Foo)   → greyed placeholder [Foo] (game substitutes at runtime)
# Escape first, then substitute against the escaped tags so raw text
# containing < or & can't break rendering.

_EM3_RE = _re_mod.compile(r"&lt;EM3&gt;(.*?)&lt;/EM3&gt;", _re_mod.DOTALL)
_EM4_RE = _re_mod.compile(r"&lt;EM4&gt;(.*?)&lt;/EM4&gt;", _re_mod.DOTALL)
_MISSION_TOKEN_RE = _re_mod.compile(r"~mission\(([^|)]+)(?:\|[^)]*)?\)")

# Frontend version chip (main-menu watermark). CIG ships a key called
# ``Frontend_PU_Version`` whose value the main menu renders verbatim.
# We append " | Localizations Enhanced with Open Strings vX.Y.Z" so
# users (and their screenshots / support tickets) can see at a glance
# that the localization has been customized. Idempotency: the stamp RE
# strips any prior watermark before re-appending, so successive applies
# and version bumps don't accumulate suffixes. Skipped silently when
# the key isn't in merged_dict.
_FRONTEND_VERSION_KEY = "Frontend_PU_Version"
_FRONTEND_VERSION_STAMP_RE = _re_mod.compile(
    r"\s*\|\s*(?:Localizations Enhanced (?:with|by)|Enhanced with <3 by)\s+Open Strings\s+v?[^\s|]+\s*$",
    _re_mod.IGNORECASE,
)


def _stamp_frontend_version(merged: dict) -> dict:
    """Append the Open Strings watermark to Frontend_PU_Version in place.

    Skips entirely if the key is not present in *merged* — we don't
    fabricate the key when stock doesn't have it. Mutates and returns
    *merged*.
    """
    if _FRONTEND_VERSION_KEY not in merged:
        return merged
    base = _FRONTEND_VERSION_STAMP_RE.sub("", merged[_FRONTEND_VERSION_KEY]).rstrip()
    merged[_FRONTEND_VERSION_KEY] = f"{base} | Localizations Enhanced with Open Strings v{get_version()}"
    return merged


def _render_preview_html(key: str, raw: str) -> str:
    """Render *raw* loc-string value as styled HTML for the preview pane."""
    if not raw:
        body = "<em style='color:#888;'>(empty)</em>"
    else:
        escaped = _html_mod.escape(raw)
        # Literal backslash-n in the INI → actual line break. Handle the
        # escape sequence as two characters, not a Python newline — the
        # parser reads lines verbatim.
        escaped = escaped.replace("\\n", "<br>")
        escaped = _EM3_RE.sub(
            r'<span style="text-decoration:underline;">\1</span>',
            escaped,
        )
        escaped = _EM4_RE.sub(
            r'<span style="font-weight:bold;color:#4a9eff;">\1</span>',
            escaped,
        )
        escaped = _MISSION_TOKEN_RE.sub(
            r'<span style="color:#888;font-style:italic;">[\1]</span>',
            escaped,
        )
        body = escaped

    return (
        '<div style="font-family:Atkinson Hyperlegible,Arial,sans-serif;font-size:10pt;line-height:1.45;">'
        f'<div style="color:#888;font-size:8pt;margin-bottom:8px;'
        f'font-family:Consolas,monospace;">{_html_mod.escape(key)}</div>'
        "<br>"
        f"{body}"
        "</div>"
    )
