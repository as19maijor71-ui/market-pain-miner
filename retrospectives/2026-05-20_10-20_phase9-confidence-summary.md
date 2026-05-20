# Retrospective: Phase 9 Confidence Summary

Date/time: 2026-05-20 10:20

## Task

Harden the first safe run by reducing review noise through narrow confidence calibration and adding one privacy-safe research summary command.

## What Changed

- Calibrated confidence for deterministic fixture-proven `pain` and `tool_mention` rule cases.
- Added `summary` CLI output for counts, clusters, solutions, opportunities, review candidates, and quality gaps.
- Added tests for reduced review noise, retained weak/offtopic review candidates, unchanged evaluate precision, and summary privacy.
- Updated the phase 7 alias-map test so it no longer depends on a pain item staying in low-confidence review.
- After fresh review, tightened calibration again so ambiguous URL/manual-work messages remain review candidates and summary reads use one SQLite snapshot.

## Result

Done.

## What We Learned

- The review queue was noisy mainly because correct rule-backed pains and tool mentions sat exactly at the review threshold.
- The useful hardening boundary is confidence calibration, not broader taxonomy changes.
- A single privacy-safe summary removes the manual copy/paste step from the fixture pipeline without adding UI or export features.
- Calibration rules need negative/ambiguous regression tests, not just happy-path fixture tests.

## Next Step

Run `summary` and `review` on one owner-provided private local export path, then compare real-world review candidates against the fixture calibration.
