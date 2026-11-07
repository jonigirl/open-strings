# TODO

## 1.5.3 Validation

- [ ] Build a fresh local smoke installer from current `main` and verify the Nov 7 changes.
- [ ] Run the 1.5.3 smoke checklist in [TESTING.md](TESTING.md) against PTU.
- [ ] Re-analyze the latest 4.10.3 PTU extraction after each meaningful patch; resolve enhancement data issues before release.
- [ ] Once 4.10.3 reaches LIVE, extract and compare LIVE data, verify generated enhancements, and complete the LIVE smoke test.
- [ ] Prepare the 1.5.3 release only after LIVE validation and all identified issues are resolved.

## Deferred Improvements

These are candidates for separate review and approval, not current release work.

- [x] Review the UI and UX for usability improvements (static review; runtime/high-DPI checks remain).
  - [x] Make every font choice, including Segoe UI, apply and persist correctly.
  - [x] Use readable, scalable body and description sizes; remove undersized fixed-pixel text overrides.
  - [x] Give enhancement cache indicators a textual and accessible state instead of relying on color alone.
  - [x] Decide the progressive-disclosure split: Basic shows core search/edit/apply actions; Advanced adds filters and less-used tools.
  - [x] Make the Log tab respect the selected appearance preferences where appropriate.
  - [ ] Test the revised UI in the built app at common resolutions and Windows scaling levels.
- [x] Make Clear Cache target the DataForge cache in LocalAppData.
- [x] Restrict Restore Backup to validated active-channel backups and preserve the current game file.
- [x] Keep the main window alive if a background worker does not stop during close.
- [x] Snapshot Apply inputs, abort on channel/data-folder changes, and roll back if post-write persistence fails.
- [x] Keep backup filenames unique when backups are created within the same timestamp interval.
- [x] Persist edits to their originating channel and prevent values carrying across channel/data-folder switches.
- [x] Limit uninstall edit cleanup to Open Strings' per-channel files and folders.
- [x] Verify downloaded unp4k against its pinned SHA-256 digest.
- [x] Run CI lint/format checks repository-wide and type-check the enhancement generator.
- [x] Run source reload and Apply-to-Game processing outside the UI thread.
- [x] Implement the confirmed Basic/Advanced split; Advanced remains the upgrade default.
- [ ] Explore additional appearance customization beyond the view-mode split.
- [ ] Audit the codebase against current best practices for open-source Python projects.
- [ ] Profile generation with real DataForge data and optimize only measured bottlenecks.
- [ ] Measure and improve extraction and enhancement-generation speed where profiling identifies bottlenecks.
- [ ] Show subtask progress as well as overall progress during multi-phase operations.
- [ ] Add an export option that excludes personal user edits so recipients can use shared localization files without Open Strings.
- [x] Move Apply to Game file processing off the UI thread.
- [ ] Split the enhancement generator after integration coverage is sufficient.
- [ ] Review candidate enhancement additions, including melee items and additional weapon statistics.
- [ ] Identify and add useful journal entries that are not currently covered.
- [ ] Verify that extraction and generation cover all commodities present in the game data.
