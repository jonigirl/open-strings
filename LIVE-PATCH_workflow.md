# LIVE Patch Validation Workflow

Use this workflow when a Star Citizen patch reaches LIVE. Compare the new LIVE data with its previous LIVE baseline and the latest validated PTU baseline, then test it against the latest Open Strings test build before deciding whether release preparation can begin.

This workflow determines readiness to build for release. It does not authorize signing, tagging, publishing, pushing, or creating a release.

## Before Starting

- Confirm the LIVE `Data.p4k` and build identity correspond to the patch under review.
- Record the latest validated Open Strings test-build version and source commit.
- Locate the previous LIVE localization and generated-output baseline and the latest PTU baseline.
- Preserve existing caches and comparison artifacts. Do not clear caches unless their identity or integrity requires rebuilding.

## Refresh LIVE Data

1. Select LIVE in Config and verify the installed game path.
2. Extract the LIVE base localization if the archive identity changed or the cache is missing. Confirm parsing succeeds and record the key count.
3. Validate the LIVE DataForge cache identity. Extract or rebuild only the layers required by the changed archive or patch set.
4. Confirm export integrity and cache health before generation.
5. Generate all intended enhancement categories. For a full release comparison, confirm all 13 enhancement INIs are present and the compatibility report reflects the current cache.

## Compare Patch Data

Compare the new LIVE base localization with the previous LIVE baseline and latest PTU:

- Record normalized added, removed, and changed key counts for each comparison.
- Check whether PTU-only keys or changed values require generator compatibility work.
- Compare DataForge record and patch identities; explain whether differences are patch data, source-code changes, or configuration.
- Keep detailed game-data values and source records in private local notes, not tracked documentation.

## Compare Generated Output

For each of the 13 enhancement INIs:

- Compare new LIVE output with previous LIVE and latest PTU output.
- Record added, removed, and changed keys and confirm emitted keys resolve in LIVE localization, except where enhancement-only keys are intentional.
- Review meaningful value changes against their DataForge fields and formatter behavior.
- Classify compatibility warnings and retain unresolved items as explicit release risks.
- Confirm each category can be enabled, disabled, and regenerated without losing saved user overrides.

## Test Build Validation

Build a local test artifact from the candidate source using the repository build instructions. A local smoke build is not a release artifact.

Using the built app or installer:

- Verify the displayed version and that the build contains the candidate source.
- Test startup, channel selection, source loading, enhancement generation, and all 13 output files.
- Check Basic/Advanced controls, appearance settings, and export behavior.
- Test missing-source handling and Apply/Restore only when deliberate; verify the backup and restore the original game file.
- Inspect selected in-game ship, component or weapon, armor, mission, and commodity output after a deliberate Apply. Restore the verified original file afterward.
- If testing an installer upgrade, confirm the prior uninstaller has finished before file replacement and the resulting uninstaller registration works.

## Release Readiness

Release preparation may begin only when:

- Full tests, coverage threshold, Ruff lint/format, and mypy gates pass.
- LIVE extraction, integrity validation, generation, and per-output comparisons are complete.
- Release-impacting differences and compatibility warnings are resolved or explicitly accepted.
- The installed test build passes the required smoke checks and selected in-game rendering checks.
- The installer, version, changelog, signatures, and bundled tools are ready for a separate, explicitly authorized release workflow.

Record the LIVE patch identity, test-build version/commit, comparison counts, output results, test findings, and remaining risks in TODO or private test notes. Do not tag, push, sign, publish, or release as part of this checklist.
