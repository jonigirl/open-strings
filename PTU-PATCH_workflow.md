# PTU Patch Validation Workflow

Use this workflow when a new Star Citizen PTU patch is available. The goal is to compare the new PTU data with its previous baseline and current LIVE, then record whether the current Open Strings test build handles the differences.

This is a validation workflow, not authorization to apply files to the game, delete caches, publish builds, or release Open Strings.

## Before Starting

- Confirm the PTU `Data.p4k` belongs to the new patch and record its build identity.
- Record the Open Strings test build version and source commit being tested.
- Locate the previous PTU localization and generated-output baseline, plus the current LIVE baseline.
- If the PTU patch identity has not changed and required caches/outputs are present and healthy, skip repeat extraction and generation and report the baseline as unchanged. If a required cache is missing or invalid, rebuild only that cache, validate it, and reuse the same patch baseline.
- Preserve existing data and output baselines. Do not clear caches merely to force a rebuild.

## Refresh PTU Data

1. Select PTU in Config and verify the installed game path.
2. Extract the PTU base localization when the PTU archive identity is new or its cache is missing. Confirm parsing succeeds and record the key count.
3. Check the PTU DataForge cache identity. Extract or rebuild it when its source identity or patch state changed, or when the cache is missing or invalid. If only the cache is damaged while the patch identity is unchanged, rebuild only that cache and reuse the same patch baseline.
4. Confirm export integrity and cache health before generating enhancements. Record failures and warnings without copying full game strings into project documentation.
5. Enable the intended enhancement categories. Generate only when the patch changed or a required output is missing or stale; if the identity, caches, and outputs are unchanged and healthy, skip generation. For a full comparison, confirm all 13 enhancement INIs are present and the compatibility report is current.

## Compare Localization

Compare the new PTU base localization with the previous PTU baseline and current LIVE:

- Normalize keys using the same parsing and variant rules as Open Strings.
- Record added, removed, and changed key counts for each comparison.
- Check that removed or changed keys do not invalidate generated enhancement entries.
- Keep detailed game-data values and source records in private local notes, not tracked documentation.

## Compare Enhancements

For each generated INI, compare the new PTU output with the previous PTU output and current LIVE output:

- Record added, removed, and changed keys.
- Confirm every emitted key exists in the PTU base localization unless the feature explicitly supports enhancement-only keys.
- Review changed values against their source fields and formatter behavior; do not infer semantics from names alone.
- For mission cooldowns, check enable flags and configured variations, identify description keys with variant-specific values, and confirm units before accepting the output.
- Classify unknown tag values, unmatched commodity names, and other compatibility warnings as supported, out of scope, ambiguous, or unresolved.
- Check whether a difference comes from the game patch, changed generator source, or changed settings before attributing it.

## App Smoke Test

Using the current local Open Strings test build:

- Confirm PTU is active and the status bar reports the expected channel.
- Confirm the table loads, Basic and Advanced modes behave as intended, and search/reset works.
- Confirm all enabled enhancement categories report Ready, Missing, or Off as appropriate.
- Check selected changed enhancement entries in the preview for readable, non-duplicated output.
- Check a mission description with cooldown data and confirm only enabled personal/abandoned timers appear with their configured variations.
- Exercise Apply/Restore only when deliberately testing that workflow; verify a backup and restore the original game file.

## Completion Record

Record the patch identity, Open Strings version/commit, extraction and generation status, localization deltas, per-file enhancement deltas, compatibility warnings, UI findings, and unresolved questions in the current TODO or private test notes. Keep prior baselines available for the next patch comparison.

PTU completion does not establish LIVE readiness. Repeat the LIVE workflow when the patch reaches LIVE.
