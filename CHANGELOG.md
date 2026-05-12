# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.1.2]: https://github.com/jonigirl/open-strings/releases/tag/v1.1.2
[1.1.1]: https://github.com/jonigirl/open-strings/releases/tag/v1.1.1
[1.1.0]: https://github.com/jonigirl/open-strings/releases/tag/v1.1.0
