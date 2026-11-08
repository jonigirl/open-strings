# TODO

## Today: Local Testing Build

- [x] Complete the deferred audits, implementation, and documentation updates; final tests and static checks pass.
- [ ] Preserve existing `build/` and `dist/` outputs, then run `scripts/build/build_all.bat` for a local smoke installer (self-signed app, unsigned installer; not a release build).
- [ ] Review and commit the tested source, tests, and docs locally after the build; do not tag or push.
- [ ] Provide the installer path and focused smoke checks for the user's manual testing; do not install it automatically.

## 1.5.3 Release Validation

Complete these gates in order. Use the current manual workflow in [TESTING.md](TESTING.md); [TESTPLAN.md](TESTPLAN.md) contains legacy 1.0-era cases and should not be run wholesale.

- [x] Build a fresh local smoke installer from committed `main` (2026-11-07); verify its bundled files and checksums.
- [x] Install and same-build upgrade the smoke build (2026-11-07, regular profile by user approval; not disposable). Verified version 1.5.3.0, custom data-folder setting, and 3 user INIs/11 backups remain. The installer handoff selects LIVE; the app rebuilt LIVE `base.ini` and loaded 90,615 entries.
- [x] Rebuild PTU caches and generate enhancements in the installed app (2026-11-07): extracted `base.ini` (91,210 stock strings), validated 118,056 exported records and 31,573 cached records, published `raw`/`pristine` DataForge layers, generated all 13 INIs (5,461 entries), and reloaded 90,879 strings. Compatibility report lists 49 unknown tag values for review. After reinstall on 2026-11-08, regenerated the 13 INIs from the preserved PTU DataForge cache.
- [x] Confirm PTU DataForge reports up to date and all 13 enhancement INIs are present after regeneration (2026-11-08).
- [x] Verify installed Basic/Advanced toggles and Basic search after upgrade (2026-11-07): `shield` showed 1,228 of 90,879 PTU strings; cleared the query and restored Advanced.
- [x] Verify font options in the installed app (2026-11-08): selected Segoe UI and OpenDyslexic, restored Atkinson Hyperlegible, and confirmed Atkinson persisted after restart.
- [x] Apply and restore PTU `global.ini` (2026-11-08): Apply created a backup; Restore used that verified backup and the game file returned to its original SHA-256. The five-backup cap pruned the two oldest backups as expected.
- [x] Decline the missing-source Apply warning in PTU (2026-11-08): Apply canceled, the game-file SHA-256 and backup count were unchanged, and the original PTU `base.ini` cache hash was restored.
- [x] Verify enhancement category states are readable as text without relying on color (2026-11-08): installed UI showed all seven `Missing` labels clearly within their bounds; Qt tests verify `Ready`, `Missing`, and `Off` text and accessible descriptions. Visual check was on LIVE; PTU output states were not rechecked.
- [x] Verify close deferral during a long operation (2026-11-08): sent `WM_CLOSE` during LIVE DataForge extraction; the app stayed responsive and continued. After extraction and validation completed, DataForge reported up to date and the app closed normally after a second `WM_CLOSE`. No Apply occurred.
- [ ] Test common resolutions and display scaling; confirm Config and Enhancements remain reachable and text is legible.
- [ ] Resolve small-window layout: at 96 DPI, resize attempts to 1280x800 and 1024x768 were constrained to about 1264x966 and 1162x966, respectively.
- [x] Resolve the Basic reset-control mismatch (2026-11-08): keep `Clear Filters` visible in Basic; verify it clears search and resets category. Focused view-mode tests pass.
- [x] Fix and regression-test the same-build upgrade stale-uninstaller bug (2026-11-08): run the old uninstall in `InitializeSetup`, wait for registry removal and the detached uninstaller's completion marker, and stop setup on failure/timeout. Inno Setup 6.7.3 compile and same-build upgrade passed; the new `unins000.exe` remained valid and no active uninstall temp folder remained. All 14 user files remained; 13 hashes matched, while LIVE `user.ini` was rewritten on app close with its 12 entries and length unchanged. Stale HKLM cleanup now fails closed if the entry remains; permission-denied runtime behavior is not tested.
- [x] Test default uninstall/reinstall in the regular profile (2026-11-08): settings JSON, all 14 user files, 11 backups, tools, and DataForge cache remained. Thirteen user-file/backup hashes matched the pre-uninstall snapshot; LIVE `user.ini` was rewritten on app close but kept its 12 entries and length. Reinstalled 1.5.3, restored PTU, and regenerated its outputs.
- [ ] Test the optional “My edits and backups” cleanup only with a disposable user-data folder; verify unrelated shared files remain untouched.
- [x] Compare LIVE/PTU localization and generated outputs (2026-11-07): PTU has 265 normalized new keys, 1 removed, and 99 changed; detailed generated deltas are recorded in the handover.
- [ ] After each meaningful PTU patch, compare localization and generated outputs with the previous baseline; resolve release-impacting data differences without repeating checks for an unchanged patch.
- [ ] Create `PTU-PATCH_workflow.md` for the usual validation of each new PTU patch, including comparison of PTU localization and generated outputs with LIVE.
- [ ] Create `LIVE-PATCH_workflow.md` for the usual validation when LIVE is patched, comparing it with the latest Open Strings test build and confirming readiness to build for release.
- [ ] When 4.10.3 reaches LIVE, extract LIVE data, compare it with PTU, validate generated enhancements, and complete the LIVE smoke test, including selected in-game rendering checks.
- [ ] Prepare the 1.5.3 release only after PTU and LIVE validation is complete and release-impacting issues are resolved.

## Deferred Work

These are not current release gates. Review scope before starting; use the dependencies below to avoid duplicate investigation or premature refactoring.

### Data coverage

- [x] Review carryable localization references across channels; distinguish mapped variants from unresolved source-data gaps without claiming full coverage.
- [x] Review compatibility-report fallbacks across channels; classify supported candidates, out-of-scope values, and ambiguous categories without changing generation behavior.
- [x] Review enhancement candidates against current generator coverage; separate verified omissions from speculative metrics and defer output changes until semantics and duplicate-text risks are checked.
- [x] Review journal coverage against current localization keys; identify data-supported candidates and preserve stock prose where source semantics or duplication remain uncertain. Base-key comparison covered both channels; DataForge candidate review was LIVE-only.

### Engineering and performance

- [x] Audit the codebase and scope follow-ups (2026-11-08): completed a risk-focused review with clean Ruff, formatting, and mypy baselines. Scoped loader-timeout ownership and concurrent settings-write risks for separate implementation; no source changes made in this audit.
- [x] Establish focused integration coverage of the actual generator entry point with temporary fixtures and stable output checks (2026-11-08). Decision: do not split or migrate into the incomplete facade now; revisit only with broader representative coverage and separately scoped work.
- [x] Profile real DataForge extraction and representative generation (2026-11-08); record measurements and optimization decision privately. No optimization was justified by this bounded run; preserve content-hash cache validation.

### User-facing improvements

- [x] Make the Default theme follow system light/dark appearance (2026-11-08): Default resolves through Qt's system scheme and refreshes the UI on scheme changes; explicit Light/Dark remain fixed. Focused theme and refresh tests pass; live Windows setting-change validation remains manual.
- [x] Confirm multi-phase operations show phase messages alongside overall progress (2026-11-08): generator checkpoints flow through `ProgressSink` to `AnimatedProgressDialog`; progress-sink and worker tests pass.
- [x] Add Applied/Shared loc-pack export modes (2026-11-08): Shared merges base localization and enabled enhancements without user edits or the Open Strings version stamp, fails on missing enabled enhancement files, and writes only the selected ZIP in a background worker. Protected input paths cannot be used as the ZIP destination; focused tests pass.
- [x] Retire the legacy [TESTPLAN.md](TESTPLAN.md) with clear archive warnings; direct current manual testing to [TESTING.md](TESTING.md).
- [x] Update [TESTING.md](TESTING.md) to list all 13 generated INIs and cover Basic `Clear Filters`, OS-following Default, and Applied/Shared export behavior.

## Completed in the 1.5.3 Work Cycle

- [x] Implement the confirmed Basic/Advanced split; Basic provides core search/category/edit/Apply, Advanced provides full filters and secondary actions, and Advanced remains the upgrade default.
- [x] Apply font, readability, and cache-status accessibility fixes; make the Log tab respect appearance preferences.
- [x] Make Clear Cache target the LocalAppData DataForge cache; validate active-channel backup restore and preserve the current game file.
- [x] Persist edits to their originating channel; prevent cross-channel/data-folder carryover; use collision-safe backup names.
- [x] Run source reload and Apply-to-Game processing outside the UI thread; snapshot Apply inputs and roll back on persistence failure.
- [x] Limit uninstall edit cleanup to Open Strings-owned per-channel files/folders; verify downloaded unp4k against its pinned SHA-256 digest.
- [x] Run repository-wide lint/format checks and type-check the enhancement generator.
- [x] Smoke-test packaged startup, mode persistence, and Basic search in an isolated profile.
