# TODO

## Today: Local Testing Build

- [x] Complete the deferred audits, implementation, and documentation updates; final tests and static checks pass.
- [x] Build a local 1.5.3 smoke installer after the Enhancements narrow-layout fix; retain the self-signed/unsigned test-only status.
- [x] User confirmed the prior four smoke checks and disposable cleanup passed.

## 1.5.3 Release Validation

Complete these gates in order. Use the current manual workflow in [TESTING.md](TESTING.md); [TESTPLAN.md](TESTPLAN.md) contains legacy 1.0-era cases and should not be run wholesale.

- [x] Build a fresh local smoke installer from committed `main` (2026-11-07); verify its bundled files and checksums.
- [x] Rebuild a local smoke installer after the Enhancements narrow-layout fix (2026-11-08); this remains a self-signed/unsigned test artifact, not a release build.
- [x] Rebuild the local 1.5.3 smoke installer after cooldown and visual fixes (2026-11-14); the app is self-signed, the installer is unsigned, and no patched tool ZIP is bundled. This is not a release artifact.
- [x] Rebuild the local test installer after changing configured personal cooldown display (2026-11-15); updated Help/generator are bundled. This remains an unsigned test artifact without the patched tool ZIP.
- [x] Fix enhancement generation after reinstall (2026-11-16): the uninstaller clears each channel cache, so generation now extracts a missing `base.ini` from `Data.p4k` before continuing. The user verified generation after reinstall with the rebuilt test installer (2026-11-16).
- [x] Install and same-build upgrade the smoke build (2026-11-07, regular profile by user approval; not disposable). Verified version 1.5.3.0, custom data-folder setting, and 3 user INIs/11 backups remain. The installer handoff selects LIVE; the app rebuilt LIVE `base.ini` and loaded 90,615 entries.
- [x] Rebuild PTU caches and generate enhancements in the installed app (2026-11-07): extracted `base.ini` (91,210 stock strings), validated 118,056 exported records and 31,573 cached records, published `raw`/`pristine` DataForge layers, generated all 13 INIs (5,461 entries), and reloaded 90,879 strings. Compatibility report lists 49 unknown tag values for review. After reinstall on 2026-11-08, regenerated the 13 INIs from the preserved PTU DataForge cache.
- [x] Confirm PTU DataForge reports up to date and all 13 enhancement INIs are present after regeneration (2026-11-08).
- [x] Verify installed Basic/Advanced toggles and Basic search after upgrade (2026-11-07): `shield` showed 1,228 of 90,879 PTU strings; cleared the query and restored Advanced.
- [x] Verify font options in the installed app (2026-11-08): selected Segoe UI and OpenDyslexic, restored Atkinson Hyperlegible, and confirmed Atkinson persisted after restart.
- [x] Apply and restore PTU `global.ini` (2026-11-08): Apply created a backup; Restore used that verified backup and the game file returned to its original SHA-256. The five-backup cap pruned the two oldest backups as expected.
- [x] Run the current test build against LIVE and PTU data and Apply to both game channels (2026-11-08; user-confirmed). User confirms both applied files are fine and has backups for emergency recovery; no restoration requested.
- [x] User reports testing the local 1.5.3 build against current LIVE and PTU (2026-11-14). This confirms a smoke test only; compatibility work for the newly released PTU is deferred until after the 1.5.3 release.
- [x] Decline the missing-source Apply warning in PTU (2026-11-08): Apply canceled, the game-file SHA-256 and backup count were unchanged, and the original PTU `base.ini` cache hash was restored.
- [x] Verify enhancement category states are readable as text without relying on color (2026-11-08): installed UI showed all seven `Missing` labels clearly within their bounds; Qt tests verify `Ready`, `Missing`, and `Off` text and accessible descriptions. Visual check was on LIVE; PTU output states were not rechecked.
- [x] Verify close deferral during a long operation (2026-11-08): sent `WM_CLOSE` during LIVE DataForge extraction; the app stayed responsive and continued. After extraction and validation completed, DataForge reported up to date and the app closed normally after a second `WM_CLOSE`. No Apply occurred.
- [x] Verify common resolutions and display scaling (2026-11-08): user confirmed the prior check passed; exact window dimensions were not recorded.
- [x] Manually verify the rebuilt test app's Enhancements tab at a narrow window size: descriptions wrap, controls do not overlap or clip, and Favorites remains reachable by scrolling. The 376x512 automated test passes; the user confirmed the manual check passed (2026-11-16).
- [x] Resolve the Basic reset-control mismatch (2026-11-08): keep `Clear Filters` visible in Basic; focused tests pass and the user confirmed the installed behavior.
- [x] Fix and regression-test the same-build upgrade stale-uninstaller bug (2026-11-08): run the old uninstall in `InitializeSetup`, wait for registry removal and the detached uninstaller's completion marker, and stop setup on failure/timeout. Inno Setup 6.7.3 compile and same-build upgrade passed; the new `unins000.exe` remained valid and no active uninstall temp folder remained. All 14 user files remained; 13 hashes matched, while LIVE `user.ini` was rewritten on app close with its 12 entries and length unchanged. Stale HKLM cleanup now fails closed if the entry remains; permission-denied runtime behavior is not tested.
- [x] Test default uninstall/reinstall in the regular profile (2026-11-08): settings JSON, all 14 user files, 11 backups, tools, and DataForge cache remained. Thirteen user-file/backup hashes matched the pre-uninstall snapshot; LIVE `user.ini` was rewritten on app close but kept its 12 entries and length. Reinstalled 1.5.3, restored PTU, and regenerated its outputs.
- [x] Test the optional “My edits and backups” cleanup only with a disposable user-data folder (2026-11-08; user confirmed passed); unrelated shared files remained untouched.
- [x] Compare LIVE/PTU localization and generated outputs (2026-11-07): PTU has 265 normalized new keys, 1 removed, and 99 changed; detailed generated deltas are recorded in the handover.
- [ ] After each meaningful PTU patch, compare localization and generated outputs with the previous baseline; resolve release-impacting data differences without repeating checks for an unchanged patch.
- [x] Create `PTU-PATCH_workflow.md` for repeatable PTU-to-prior-PTU and PTU-to-LIVE validation (2026-11-08).
- [x] Create `LIVE-PATCH_workflow.md` for repeatable LIVE-to-prior-LIVE and LIVE-to-PTU validation and test-build release-readiness checks (2026-11-08).
- [x] Validate current LIVE data for the 1.5.3 candidate (2026-11-14): the current base and all 13 enhancement outputs exist, and the parser found no generated keys missing from the base. Exact patch identity and counts are kept in private test notes.
- [x] Show configured personal post-success cooldowns regardless of the initial flag, and abandonment cooldowns when re-acceptance is allowed; include variations and identify shared-description variants with differing values.
- [x] Confirm abandonment cooldowns in game (2026-11-16): the user confirmed three examples. Personal post-success cooldowns remain an accepted known risk below.- [x] Accept the personal-cooldown display check as a known 1.5.3 risk by user decision (2026-11-16): a positive configured personal cooldown with `hasPersonalCooldown` initially false is covered by automated tests but not yet confirmed in a live mission description. This does not establish the live repopulation interval.
- [x] Accept the LIVE cooldown-source discrepancy as a known 1.5.3 risk by user decision (2026-11-16). Current LIVE contract data marks personal cooldown disabled for the target variants despite an observed runtime of more than an hour; a full, manifest-validated LIVE DataForge export found no alternate static cooldown source (details in private notes). Do not claim the displayed personal cooldown matches the runtime interval. After 1.5.3, verify by recording the variant and time to repopulate after completion versus abandonment, and confirm the authoritative source and units.
- [x] Waive previous-LIVE and pre-5.0 PTU comparisons for 1.5.3 by user decision (2026-11-14): the old PTU data was removed when the new PTU data replaced it, and missing these comparisons is accepted for this release. Do not claim the new PTU is compatible.
- [x] Review the current LIVE fallback report (2026-11-14): 49 item-type values use 28 inferred three-letter tokens, with 10 token collisions across related labels; there are no class fallbacks. The user reports all manual checks passed. Treat these as approximate display annotations, not item classification; no behavior change is warranted for this release.
- [x] Fix the Enhancements category label rendering in the tab and startup prompt by escaping the Qt ampersand mnemonic; the checkbox displays `Armor & Suits` as literal text.
- [x] Make DataForge cached-record health checks report determinate progress through the same styled bar used for other measured phases.
- [x] Complete selected in-game rendering checks for representative ship, component/weapon, armor, mission, and commodity enhancements; the user confirmed they render correctly (2026-11-16).
- [x] Verify the rebuilt app's visual changes, including the literal `Armor & Suits` label and determinate cached-record progress; user confirms visual changes passed (2026-11-14).
- [x] Include the current tool-download changes in the 1.5.3 candidate; the combined worktree passes the full test suite, Ruff, formatting, and mypy. Rebuild after the remaining sign-off checks.
- [x] Build the signed 1.5.3 release installer (2026-11-16): app and installer signatures are valid and timestamped with the Certum certificate. No tool ZIP is bundled; the app downloads the pinned unforge package from the v1.5.2 release, whose published SHA-256 matches the pin, and downloads unp4k normally.
- [ ] Prepare the 1.5.3 release after rebuilding with final docs, confirming installer signature and bundled tools, and completing the separately authorized tag/publish steps. Manual checks pass per user; the historical comparison gap is explicitly waived and the cooldown items are accepted known risks. Compatibility with the new PTU patch remains out of scope until after 1.5.3.

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

- [x] Make the Default theme follow system light/dark appearance (2026-11-08): Default resolves through Qt's system scheme and refreshes the UI on scheme changes; explicit Light/Dark remain fixed. Focused theme and refresh tests pass; the user confirmed the live appearance check.
- [x] Confirm multi-phase operations show phase messages alongside overall progress (2026-11-08): generator checkpoints flow through `ProgressSink` to `AnimatedProgressDialog`; progress-sink and worker tests pass.
- [x] Add Applied/Shared loc-pack export modes (2026-11-08): Shared merges base localization and enabled enhancements without user edits or the Open Strings version stamp, fails on missing enabled enhancement files, and writes only the selected ZIP in a background worker. Protected input paths cannot be used as the ZIP destination; focused tests pass and the user confirmed both modes.
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
