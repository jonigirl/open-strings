# Open Strings Roadmap

> Upstream Smart Citizen history (0.1.x – 1.0.0) is in [UPSTREAM-HISTORY.md](UPSTREAM-HISTORY.md).

## Status: Active Development

Open Strings has returned to active development targeting Star Citizen 4.8.

## 1.3.0 — Return to Active Development ✓ Released 2026-05-20

_Star Citizen 4.8 compatibility and new features._

- [x] `Frontend_PU_Version` watermark written to `global.ini` on Apply — marks producing version and SC build
- [x] `g_language` detection is now case-insensitive (`g_Language`, `G_LANGUAGE`, etc.)
- [x] `os.path.normpath()` applied at all path-setting call sites in Config tab to prevent double-separator paths
- [x] "Preview Merge" renamed to "Preview Apply" throughout Config tab UI
- [x] Apply dialog shows per-category enhancement counts
- [x] `should_autosave_user_ini()` guard — suppresses unnecessary `user.ini` writes when nothing changed
- [x] Blueprint scanner widened to full `blueprintrewards/` subtree for SC 4.8 compatibility
- [x] Versioned lookup cache to invalidate stale generator caches across SC releases
- [x] DataForge diff-cache (`dataforge_diff.py`) — SHA-256 snapshot manifest; enhancement generators skip unchanged categories
- [x] DataForge cache relocated to `%LOCALAPPDATA%\Open Strings\<channel>\cache\dataforge` (outside OneDrive scope)
- [x] `dataforge_patcher.py` switched from `xml.etree.ElementTree` to `lxml.etree`
- [x] Python 3.12 `shutil.rmtree` onexc compat fix

## 1.2.0 — Upstream v1.3.0 port + code quality

- [x] Export Loc-Pack button — packages applied `global.ini` as a shareable zip
- [x] Enhanced status badge — Status column distinguishes auto-generated (`Enhanced`, blue) from user edits (`Modified`, green)
- [x] Mission Engagement Type — `FPS` / `Ship` / `FPS & Ship` derived from loc-key naming in enhancements generator
- [x] Mission Turret counts — turret counts and hostility from DataForge spawn XML in mission stats block
- [x] Tutorial Skip persists across app version updates
- [x] Preview pane height cap raised to 120 px; Config/Enhancements tabs no longer let preview consume all vertical space
- [x] Dedup `_COMPONENT_CODES` — single source of truth in `string_model.py`
- [x] Import INI: `urlretrieve` replaced with size-capped HTTPS-enforced downloader
- [x] Bugbear ruff rules (`B`) added; all violations resolved
- [x] Dead code removed: `source_category_filters` block, `test_category_extraction()` function
- [x] mypy `attr-defined` error on `QCoreApplication.setFont` resolved

## 1.1.0 — Initial Fork Release

- [x] Fork from Smart Citizen 1.0.0 (Osiris DevWorks)
- [x] Rebrand to Open Strings — app name, window title, About/Help documentation, data directory (`Documents\Smart Citizen\` → `Documents\Open Strings\`)
- [x] Remove Smart Citizen / Osiris DevWorks branding, donation links, and ODW Discord references
- [x] Remove unused upstream splash image
- [x] Add Check for Updates — checks `jonigirl/open-strings` GitHub releases on startup (6-hour interval) and via toolbar button
- [x] Change journal annotation tag from `[SmC]` to `[OS]`

## 1.1.1 — Attribution and legal patch

- [x] Add MIT attribution for bundled unp4k / unforge tools to NOTICE.md
- [x] Add RSI / Data.p4k disclaimer to README
- [x] Install LICENSE and NOTICE.md alongside app via installer

## 1.1.2 — Upstream fixes port + maintenance

- [x] Port radar name tags from upstream 1.1.0: `[CLASS-S{size}-{grade}]` annotations for radar components, matching the existing pattern for shields, power plants, coolers, and quantum drives
- [x] Port radar sibling-key propagation from upstream 1.1.0: `"RADR"` added to `comp_types` so radar stat blocks propagate from `_SCItem` keys to their non-SCItem siblings
- [x] Fix Custom Value cell editor losing content on double-click: `EditRole` now returns `entry.custom_value` in `StringTableModel.data()`, preventing the delegate from receiving `None` and erasing unsaved text
- [x] Fix Generate Enhancements and source reload wiping pending edits: snapshot/restore mechanism preserves un-Applied in-memory edits across all `_on_loading_finished` and `perform_merge_and_reload` paths
- [x] Update unp4k / unforge to v4.0.83 (self-contained .NET 10 binaries)
- [x] Runtime tool download: unp4k and unforge are no longer bundled in the installer; they are downloaded once on first extraction to `%APPDATA%\Open Strings\tools\` and reused automatically
- [x] Fix quantum drive stats loss: entities whose XML `Localization` points to the `_SCItem` key variant (e.g. `item_DescQDRV_ARCC_S03_Fissure_SCItem`) now have stats propagated directly to the plain canonical key the merger picks (`item_DescQDRV_ARCC_S03_Fissure`), preventing silent discard. Affected 11 drives (Fissure, Impulse, Agni, Vesta, Drifter, Wanderer, Ranger, Erebos, Metis, Tyche, Balandin)
- [x] Dynamic component type derivation: `comp_types` in the `_SCItem` propagation loop is now derived from base.ini key patterns at generation time rather than a hardcoded tuple — new component categories CIG adds in future patches are picked up automatically
- [x] Zero-match warning: `scan_entity_dir` now logs a `WARNING` when a component directory produces 0 augmented entries despite finding loc-key matches, surfacing XML structure changes immediately at generation time
- [x] Add `scripts/audit_dataforge_attrs.py` — patch testing tool that dumps all DataForge XML element·attribute pairs per component category and diffs them against a previous snapshot to identify new or removed attributes. See TESTING.md for the post-patch workflow
- [x] Configurable data folder — new "Open Strings Data" control in Config tab (Browse / Reset) lets users move `user.ini`, cache, DataForge extraction, and backups off OneDrive-synced Documents without manual registry editing. Persisted as `user_data_dir` in registry; `UserDataDir` alias migrated lazily on first read. Based on upstream PR #3 by Coerwyn.
- [ ] Test and verify compatibility with Star Citizen 4.8
- [ ] Review and update localization tag handling for any 4.8 changes

### Testing infrastructure (completed during 1.1.0 → 1.1.1)

- [x] Pytest config consolidated into `pyproject.toml`; `tests/pytest.ini` removed
- [x] Coverage floor enforced at 65%; GUI files excluded from measurement
- [x] GitHub Actions CI: lint on ubuntu, tests on windows; uv caching; coverage.xml artifact
- [x] `StringTableModel` covered by 85 automated tests via `pytest-qt`; two Qt compliance bugs found and fixed
- [x] `ini_parser.py` coverage raised from 54% to 93% with 13 new tests
- [x] Overall non-GUI coverage: 88% across 413 tests

## Future / Backlog
