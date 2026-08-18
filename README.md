# Open Strings

_Customize Star Citizen's localization strings._

## Fork notice

Open Strings is a fork of [Smart Citizen by Osiris DevWorks](https://github.com/Osiris-DevWorks/smart-citizen), modified by Joni Hayes. Distributed under GPL-3.0-only.

## Features

- **Multi-channel support** — LIVE / PTU / EPTU / HOTFIX / TECH-PREVIEW each get an isolated workspace (independent `user.ini`, cache, backups, DataForge extraction, enhancement INIs).
- **Sourced from Data.p4k** — stock localization and DataForge entity data are unpacked directly from your installed game; no community mirrors, no network needed.
- **Inline editing with live preview** — double-click any cell to edit; preview pane renders loc-tokens (line breaks, EM3/EM4 emphasis, mission placeholders) as styled HTML.
- **Launcher menu heading** — rename the heading shown in the Star Citizen launcher; optionally show the Open Strings version suffix.
- **Auto-generated enhancements** — stat overlays for ships, components, weapons, missions, journal entries, and commodity crafting; togglable per category.
- **Safe apply** — timestamped backups before every write, automatic rollback on validation mismatch, up to 5 backups per channel.

## Data And Cache

Your editable data, backups, and generated enhancement INIs live under your selected
Open Strings data folder, normally `Documents\Open Strings\<channel>\`. The larger
DataForge XML cache is stored separately at `%LOCALAPPDATA%\Open Strings\<channel>\cache\dataforge`
to keep it outside OneDrive-synchronised Documents.

DataForge uses a protected two-layer cache: a pristine extraction and a patched working
copy. Game or extraction-tool updates rebuild both layers; an Open Strings patch update
rebuilds only the working copy before regenerating enhancements.

## Download & Installation

**Important:** Current releases are **not code-signed**. Windows Defender SmartScreen will show a warning on first launch. This is expected — Open Strings is a hobby project and code-signing certificates cost money. You can safely bypass the warning by clicking "More info" → "Run anyway" if you trust the source.

A trusted code-signing certificate is planned for future releases.

## Install (from source)

Requires Python 3.12+, [UV](https://docs.astral.sh/uv/getting-started/installation/), and Windows 10/11.

```bash
uv sync
uv run python src/main.py
```

## Verification

```bash
uv run pytest
```

The suite includes unit, integration, and Qt tests. The enforced coverage floor is 83%.
See [TESTING.md](TESTING.md) for manual patch-validation steps.

## Build

See [scripts/build/BUILD_INSTRUCTIONS.md](scripts/build/BUILD_INSTRUCTIONS.md).

## Legal notice

Star Citizen and all associated game data, including `Data.p4k`, are the
property of Cloud Imperium Rights LLC and Cloud Imperium Rights Ltd. Open Strings
only reads game files from your own licensed installation and does not redistribute
any RSI or CIG content. Your use of Star Citizen game data is governed by the
[Star Citizen EULA](https://robertsspaceindustries.com/eula).

This is an unofficial fan tool, not affiliated with or endorsed by Cloud Imperium
Games or Roberts Space Industries.

## Licence

GPL-3.0-only. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
