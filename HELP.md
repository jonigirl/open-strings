# Open Strings — Quick Start Guide

## First Time Setup

On launch, Open Strings reloads any customizations from your previous session and checks for your Star Citizen installation — the installer pre-fills this path, but you can change it in the **Config** tab. All stock localization and DataForge data is sourced **directly from your installed `Data.p4k`**; no game data is downloaded from community mirrors. Extract once after install and after each game patch.

## 1. Extract Base Localization from Data.p4k

Open the **Config** tab and click **Extract from Data.p4k**. This unpacks stock `global.ini` plus the DataForge entity XMLs used by the enhancement generator — ships, components, weapons, missions, blueprints, etc.

> **Extraction tools:** Open Strings downloads upstream unp4k and a pinned patched
> unforge package when the required tool version is not cached. The patched package
> comes from the app's bundled ZIP when available, otherwise from the Open Strings
> release, and its SHA-256 checksum is verified before
> extraction. No separate .NET installation is required.

Updating to 1.5.2 requires one DataForge rebuild for each channel you use. The older
cache does not contain all newly retained record bodies; your saved overrides are
not removed. A new extraction is validated before it replaces the previous cache.

When extraction finishes, the extracted `base.ini` is loaded into the table automatically — merged with any enhancement files and your saved `user.ini` overrides.

## 2. Edit Localization Strings

- Double-click any **Custom Value** cell to edit text.
- **Default Value** — original text from `Data.p4k`-extracted `base.ini`.
- **Current Value** — the effective value before your override (base + any imported INI layers).
- **Custom Value** — your personal edit. Saved automatically on every change and persisted to `<data folder>\<channel>\user.ini` (the data folder defaults to `Documents\Open Strings`; each Star Citizen channel — LIVE, PTU, EPTU, HOTFIX, TECH-PREVIEW — has its own isolated overrides).
- Edits are highlighted with a **Modified** status (green).

### Launcher Menu Heading

The **Menu Heading** field above the table changes the heading shown at the top of
the Star Citizen launcher menu. Click **Reset** to restore the stock heading. By
default, Open Strings appends its version when you apply changes; clear **Show Open
Strings version** to keep the heading exactly as you entered it.

## 3. Preview Pane

The **preview pane** in the top-right shows the rendered text of whatever row is currently selected. The game's loc-string tokens are translated into styled HTML so you see roughly how your string will read in-game:

- `\n` → line break
- `<EM3>...</EM3>` → underlined section heading
- `<EM4>...</EM4>` → bold blue inline emphasis (typically stat values)
- `~mission(Name)` → greyed `[Name]` placeholder (the game substitutes the actual value at runtime)

The pane stays visible across all tabs and reflects the last row you selected in the **String Editor** — useful for checking how a long mission description or journal entry will format before you apply.

## 4. Categories

Use the **Category** filter to focus on one domain:

- **Ships** — Ship names and descriptions (`vehicle_Name*`, `vehicle_Desc*`, plus Wikelo/Collector mods).
- **Ship Items** — Shields, power plants, coolers, quantum drives, jump drives, ship weapons, missiles, bombs, turrets.
- **Missions** — Mission briefings, contract text, reward descriptions.
- **Gear** — FPS weapons, armor, helmets, suits, optics.
- **Commodities** — Trade goods and crafting materials.
- **Journal** — In-game journal / Galactapedia-style entries.
- **Other** — Everything else.

## 5. Search & Filter

- Use the **search box** to find strings by key or text content.
- Combine with **Category** and **Status** (Enhanced / Modified / Unmodified / New) filters.
- Check **Hide Unmodified** to focus on your own edits only.
- **Category**, **Favourite**, and **Status** column dropdowns select exact values.
- Text columns have **Contains**, **Exact**, **Starts with**, and **Excludes** match
  modes. Matching is case-insensitive; column conditions are combined.
- **Clear Filters** resets both the column inputs and their match modes.
- Click any column header to sort by that column. Click the **★** header to sort favorites to the top.

## 6. Ship Favorites

- Click the **★** column on any Ship row to mark it as a favorite.
- Favorited ships get a configurable prefix prepended to their name, sorting them to the top of the in-game ship list.
- Change the prefix character in the **Enhancements** tab (default: `*`).

## 7. Apply Changes to Game

Click **Apply to Game** to write your edits to the game installation. A timestamped backup of the current `global.ini` is created in `<data folder>\<channel>\backups\` before anything is overwritten.

## 8. Restore a Backup

Click **Restore Backup** to revert to a previous version. Open Strings keeps up to **5 automatic backups** — the oldest is pruned as new ones are created.

## 9. Clear Localization

Click **Clear Localization** to delete the custom `global.ini` from the game directory, reverting the game to its default (vanilla) text. Your saved overrides in `<data folder>\<channel>\user.ini` are untouched and can be re-applied anytime.

## 10. Import INI

Use **Import INI** in the **Config** tab to fold an existing INI file into your overrides. A conflict-resolution dialog lets you decide, per key, whether to **keep current**, **use imported**, **append**, **prepend**, or provide a **custom** value.

## 11. After Game Updates

When Star Citizen updates, your edits are preserved in `<data folder>\<channel>\user.ini`. Re-run **Extract from Data.p4k** to pull fresh stock strings from the patched game — the table reloads automatically and your customizations re-apply on top.

## Enhancements Tab

- Toggle stat overlays that append numerical stats to descriptions — SCM speed, shield HP, DPS, cargo capacity, blueprint pools, mission XP, and more.
- Enable or disable each enhancement category independently.
- Configure the ship favorites prefix character.
- Click **Generate Enhancements** to extract DataForge data from `Data.p4k` and rebuild the enhancement INI files. Declarative patches under `patches/` are re-applied idempotently on every regen so known CIG data bugs stay fixed without waiting for a game patch.
- Mission descriptions distinguish temporary blueprint access from permanent
  blueprint rewards, and show successful vehicle rentals with their duration.
- DataForge export output appears live in the Log tab. An export may run for up
  to two hours overall; it stops after 30 minutes without output. Timeout messages
  distinguish these limits and include the latest diagnostics. No incomplete
  extraction is activated.

## Config Tab

- **Appearance** — pick the app theme (see below).
- **Star Citizen Installation** — path to your LIVE directory; auto-detected at install time, editable here.
- **Open Strings Data** — folder for `user.ini`, base localization, enhancement INIs, and backups. Defaults to `Documents\Open Strings`. The larger DataForge cache is kept separately under `%LOCALAPPDATA%\Open Strings\<channel>\cache\dataforge`.
- **Base Localization (P4K Extraction)** — click **Extract from Data.p4k** to unpack stock localization plus DataForge entity data directly from your installed game. This is the sole source for base strings and enhancement data.
- **Import INI** — fold an existing INI file into your overrides via the conflict-resolution dialog.

## Log Tab

- Real-time application log.
- Filter by log level, auto-scroll to latest entries, and **Export** the log for troubleshooting or bug reports.
- Click **Pop Out** to monitor the same log in a separate non-modal window while
  using the app. **Return to Tab**, or closing the window, restores the viewer
  without discarding entries.

## Themes

Pick a theme in the **Config tab → Appearance** section:

- **Default** — a deep-navy cyber theme inspired by Star Citizen's mobiGlas UI.
- **Light / Dark** — classic UI themes.

## Status Bar

Shows the count of loaded / modified entries and the state of any running background worker (extract, generate, apply).

## Guided Tour

Click the **Tutorial** button on the toolbar at any time to replay the guided tour — a step-by-step walkthrough of the core workflow with on-screen callouts pointing at each control. The tour also runs automatically the first time you launch a new version, so a fresh install never lands cold. Hit **Skip** any time to dismiss it.

## Keyboard Shortcuts

- **Ctrl+Shift+C** — Copy filtered rows to clipboard (key=value format).

## Troubleshooting

- **Nothing in the table** — Make sure **Extract from Data.p4k** has completed and the post-extract reload has finished, then check the **Log Tab** for parse errors.
- **Enhancements empty or missing items** — Run **Generate Enhancements** from the Enhancements tab; it needs a DataForge cache (click **Extract from Data.p4k** first if you haven't).
- **Apply to Game fails** — Confirm the Star Citizen install path in the **Config Tab** and that the game isn't running.
- **Stale data after game update** — Re-run **Extract from Data.p4k**, then regenerate enhancements.
- **Export integrity check failed** — The new extraction was not activated. Keep
  the previous cache and inspect the log; do not treat an incomplete export as
  current data.
- **Unresolved game references** — Some targets are absent from the game database,
  and cyclic structures cannot be represented as an infinitely expanded XML tree.
  Complete record export is not a promise that every reference resolves.

## Known Issues

Some mission text anomalies originate in Star Citizen's own data (wrong loc-key references in CIG's contract records). The game reads contracts from its own `Data.p4k` at runtime, so Open Strings can't change which loc-key the game looks up — it can only edit the _text_ under each loc-key. Where practical, we work around these by merging the intended content into the loc key the game actually reads.

- **Jorrit Dossier — "Updated Power Usage Data" shows Energy Anomaly text** — CIG Issue Council [STARC-176797](https://issue-council.robertsspaceindustries.com/projects/STAR-CITIZEN/issues/STARC-176797). CIG's `Hockrow_FacilityDelve_P2M4-Stanton4_Repeat` contract points its `Description` parameter at `@Hockrow_FacilityDelve_P2M1_Repeat_desc` instead of its own `P2M4_Repeat_desc`, so in-game players see P2M1's Energy Anomaly flavor text for a mission titled "Power Usage Data". Open Strings works around this in two steps, both declared in `patches/contracts/contractgenerator/mercenary_guild/hockrowagency/hockrowagency_facilitydelve.patch.json`:
  1. A DataForge XML edit so our enhancement generator attaches the correct P2M4 blueprint pool (Corbel Smolder, Geist Rogue/Whiteout) to `P2M4_Repeat_desc` instead of collapsing onto P2M1's.
  2. A loc-string workaround that appends `P2M4_Repeat_desc`'s full content (its flavor text plus its own blueprint pool) onto `P2M1_Repeat_desc`, separated by a labeled divider. Because the game reads the bugged pointer and looks up `P2M1_Repeat_desc` for both contracts, the P2M4 contract now displays its intended content. P2M1 players see the P2M4 block as a labeled appendix after their own description — noisier, but both contracts now show the right blueprint pool and the right flavor text.

  When CIG corrects STARC-176797, the whole patch file can be deleted and the next regenerate produces clean split descriptions again.
