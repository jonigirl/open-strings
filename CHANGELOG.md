# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-08-18

### Added

- A dedicated launcher menu-heading editor with a reset action and an optional
  Open Strings version suffix.
- DataForge now keeps a protected pristine extraction plus a patched working
  layer, allowing patch changes to rebuild enhancements without re-extracting
  `Data.p4k`.
- DataForge cache health checks verify essential XML before staged cache data
  becomes live.

### Fixed

- Component name tags now support new Star Citizen 4.10 class and item-type
  metadata, including a compact fallback for future unrecognised values.
- Apply validation accepts expected enhancement overlay keys while still
  rejecting missing stock keys.
- Overlapping DataForge paths regenerate every dependent enhancement category.
- Enhancement regeneration now detects changed base localization text.
- Generated INIs, user overrides, manifests, and downloaded source files use
  atomic replacement to preserve existing data on write failure.

## [1.4.2] - 2026-06-22

### Fixed

- Tool downloads now use the Windows certificate store for SSL verification,
  resolving download failures on systems with outdated CA bundles or antivirus SSL inspection
- Mission reputation track now renders a readable fallback label instead of empty text
  when upstream data contains unresolved placeholders (`← PLACEHOLDER →` and related variants)

## [1.4.1] - 2026-06-22

### Changed

- Enhancement generator pipeline refactored: extracted shared utilities, decomposed
  main() into testable EnhancementPipeline class, added StatLineBuilder for DRY
  formatting, full mypy strict type safety compliance

## [1.4.0] - 2026-06-17

### Fixed

- Restoring a backup no longer crashes — the reload after restore now correctly
  uses the async loading path instead of a stale direct API call
- Startup freshness checks (DataForge, enhancements) no longer raise AttributeError

  # Changed

- Internal architecture: extracted AppConstants, ApplyEngine, CategoryClassifier,
  FileUtils, PreviewRenderer, StartupFlowManager, and ResourceUtils into dedicated
  modules for maintainability
- Enhancement generator pipeline refactored: extracted shared utilities, decomposed
  main() into testable EnhancementPipeline class, added StatLineBuilder for DRY
  formatting, full mypy strict type safety compliance
- Test coverage floor raised to 83%
- Build scripts now support signing with a trusted code-signing certificate
  (`build_all.bat --sign`); self-signed builds automatically clean up after themselves

## [1.3.9] - 2026-05-20

### Added

- Installer now reads the RSI Launcher's settings file to auto-detect the Star Citizen
  install path during setup — most users no longer need to browse for it manually
- App settings also fall back to the RSI Launcher path on first launch if no path
  has been configured
- Uninstaller now offers to remove the DataForge game data cache (~1.4 GB) as an
  optional cleanup step

### Fixed

- App settings are now stored as a plain JSON file in `%APPDATA%` instead of the
  Windows registry — settings survive reinstalls and are portable between machines
- Star Citizen install path chosen during installation is now correctly applied on
  the app's first launch — previously it was silently ignored when a `settings.json`
  already existed from a prior install
- Workers module failed to load on startup due to a stale import reference introduced
  when the string-loading service was moved — corrected
- Status bar text was clipped on narrower windows; body font size increased to 11 pt
- Variant string resolution now prefers the richer (longer) value when an `_SCItem`
  mirror key and its canonical form conflict — prevents short or empty values winning

### Changed

- Activity spinner in the status bar now alternates between light blue and light
  pink while operations are in progress

## [1.3.1] - 2026-05-20

### Fixed

- Enhancements generation crashed with `No module named 'xml.etree'` in the built executable — `generate_enhancements_ini.py` is bundled as a data file so PyInstaller does not analyse its imports; `xml.etree.ElementTree` lost its only analysed reference when `dataforge_patcher.py` switched to `lxml` in 1.3.0, so it was silently dropped from the bundle. Added `xml.etree.ElementTree` to `hiddenimports` in `OpenStrings.spec`.

## [1.3.0] - 2026-05-20

### Added

- `Frontend_PU_Version` watermark written into `global.ini` on every Apply — marks which Open Strings version produced the file and stamps the SC build version alongside it
- `src/utils/dataforge_diff.py` — diff-cache module: SHA-256 snapshot manifest for the DataForge XML cache; `update_manifest()` and `dirty_categories()` enable enhancement generators to skip unchanged categories on subsequent runs
- DataForge cache directory relocated to `%LOCALAPPDATA%\Open Strings\<channel>\cache\dataforge` to keep the ~1.4 GB XML tree outside OneDrive sync scope; one-shot startup migration from the old Documents path
- Apply dialog per-category enhancement breakdown (Ships, Components, etc.) with category counts
- `should_autosave_user_ini()` guard — suppresses unnecessary `user.ini` writes when no entries changed and the on-disk file is non-empty
- Blueprint scanner widened to include the full `blueprintrewards/` subtree for SC 4.8 compatibility
- `_name_from_blueprint_filename()` helper resolves display names for blueprint reward files
- `entity_names_by_filename` third return value from `build_scitem_lookups` for bare-key `_SCItem` mirror in component generation
- `scripts/diff_mission_rewards_channels.py` — diagnostic script for comparing blueprint rewards channels across SC builds
- Versioned lookup cache (`_LOOKUP_VERSIONS`) keyed by `"<version>:<fingerprint>"` to invalidate stale generator caches across SC releases
- 11 new tests for `Frontend_PU_Version` watermark behaviour (`tests/test_frontend_version_stamp.py`)

### Fixed

- `CATEGORY_SUBTREES` paths in `dataforge_diff.py` were all missing the `foundry/records/` prefix — `dirty_categories()` always returned an empty set, so enhancement generators never re-ran after a DataForge update; all 7 entries corrected with 22 regression tests (`tests/test_dataforge_diff.py`)
- `TimeoutError` handler in `updater.py` logged "Download timeout, retrying…" but immediately re-raises with no retry; message corrected to "Download timed out"
- Duplicate `logger.error` call in `clear_cache` DataForge deletion error handler removed (copy-paste bug)
- `g_language` key detection in `user_cfg.py` is now case-insensitive via regex (`g_Language`, `G_LANGUAGE`, etc. all matched correctly)
- `os.path.normpath()` applied at all five path-setting call sites in `config_tab.py` to prevent double-separator paths on Windows
- Enhancement generation worker now skips unchanged categories instead of always regenerating all — reduces unnecessary DataForge re-processing after clean extractions
- DataForge extraction worker progress dialog now stays open across the extraction→enhancement handoff and closes correctly on failure
- "Copy Filtered" clipboard export now shows the true stock base.ini value in the "Original Value" column (previously showed the merged effective value for both "Original Value" and "Current Value")

### Changed

- Preview pane and Help/About panels now render with Atkinson Hyperlegible font (previously Segoe UI)
- Log export filename changed from `sc_loc_editor_{timestamp}.log` to `open_strings_{timestamp}.log`
- "Preview Merge" renamed to "Preview Apply" throughout the Config tab UI
- "Smart Citizen Enhancements" label updated to "Open Strings Enhancements" in Apply dialog
- Apply success dialog shows per-category enhancement counts via `collections.Counter`
- `dataforge_patcher.py` switched from `xml.etree.ElementTree` to `lxml.etree` for XML processing
- `shutil.rmtree` onexc callback uses a compat constant (`_RMTREE_CB_KWARG`) for Python 3.12 compatibility
- `lxml >= 6.1.1` added as a dependency

## [1.2.0] - 2026-05-12

### Added

- Export Loc-Pack button — packages the applied `global.ini` as a shareable zip from the toolbar
- Enhanced status badge — Status column now shows `Enhanced` (blue) for auto-generated enhancements entries and `Modified` (green) only for user edits
- Mission Engagement Type — enhancements generator derives `FPS`, `Ship`, or `FPS & Ship` from mission loc-key naming and includes it in the mission stats block
- Mission Turret counts — enhancements generator extracts turret counts and hostility from DataForge spawn XML and includes them in the mission stats block

### Fixed

- Tutorial Skip preference now persists correctly across app version updates
- mypy attr-defined error: `QCoreApplication` narrowed to `QApplication` before `setFont` call in `theme.py`
- Import INI download: replaced deprecated `urlretrieve` with size-capped HTTPS-enforced downloader (50 MB cap)
- Tools download: `urlopen` now uses `timeout=60` — worker thread can no longer hang indefinitely on a stalled server

### Changed

- Preview pane height cap raised to 120 px
- Config/Enhancements tabs no longer allow the preview pane to consume all vertical space
- `_COMPONENT_CODES` defined in one place (`string_model.py`) and imported by `ini_merger.py` — eliminates silent category-mismatch risk when new SC component types are added
- Ruff bugbear (`B`) rules added to linting — catches real coding bugs at commit time
- Removed dead `source_category_filters` block from `ini_parser.py` (all values were `None`; filtering branch was unreachable)
- Removed dead `test_category_extraction()` function from `string_model.py`
- `pak_extractor.py` bare-except blocks in freshness check now log at DEBUG level
- `version.py` VERSION.TXT read failure now logs at DEBUG level

## [1.1.2] - 2026-05-07

### Added

- Atkinson Hyperlegible as default body font with OpenDyslexic opt-in via Appearance settings
- Configurable data folder setting
- Atkinson Hyperlegible OFL attribution in NOTICE.md

### Fixed

- Header repaint stuck after layout pass
- Upgrade uninstall race condition
- QD stats loss; dynamic `comp_types`; zero-match warning
- Zip path traversal and tool gate re-entry issues
- Installer: `CurFinished` → `CurStepChanged`, `ScaleX/Y`, dead code removal
- Uninstall dialog: correct `CreateCustomForm` signature, remove `TBevel`
- Inno Setup batch parser error (goto labels instead of parenthesised else block)
- `TProgressBarStyle` → `TNewProgressBarStyle` in installer Pascal script

### Changed

- Preserve pending edits across Generate Enhancements and source reload
- Radar name tags and sibling-key propagation ported from upstream 1.1.0

## [1.1.1] - 2026-03-01

### Added

- Checkbox uninstall dialog for tools and edits cleanup
- `--no-prompt` flag to `build_exe.py`

### Changed

- Download unp4k/unforge at runtime instead of bundling binaries
- Bundled unp4k.exe updated to v4.0.83
- Signing prompt moved to start of `build_all.bat`
- Improved first-launch experience: auto-detect SC path, no error dialog on missing base.ini

### Fixed

- SC auto-detect reverted to standard paths only (removed unreliable drive scan)
- Concurrent.futures missing from PyInstaller bundle

## [1.1.0] - 2026-01-15

### Added

- Multi-channel support (LIVE / PTU / EPTU / HOTFIX / TECH-PREVIEW) with isolated workspaces
- Localization sourced directly from Data.p4k; no community mirrors required
- Inline editing with live preview rendering loc-tokens as styled HTML
- Auto-generated enhancements for ships, components, weapons, missions, journal, and commodities
- Safe apply with timestamped backups and automatic rollback on mismatch
- Check for Updates feature
- Test suite with CI coverage enforcement

[1.3.9]: https://github.com/jonigirl/open-strings/compare/v1.3.0...v1.3.9
[1.3.1]: https://github.com/jonigirl/open-strings/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/jonigirl/open-strings/releases/tag/v1.3.0
[1.2.0]: https://github.com/jonigirl/open-strings/releases/tag/v1.2.0
[1.1.2]: https://github.com/jonigirl/open-strings/releases/tag/v1.1.2
[1.1.1]: https://github.com/jonigirl/open-strings/releases/tag/v1.1.1
[1.1.0]: https://github.com/jonigirl/open-strings/releases/tag/v1.1.0
