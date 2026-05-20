# Retrospective: Phase 8 Local Research Run

Date/time: 2026-05-20 09:13

## Task

Run the post-MVP CLI pipeline safely, validate expected labels if available, and identify MVP hardening gaps before dashboard/CSV/FTS work.

## What Changed

- Added `plans/2026-05-20-phase8-local-research-run.md`.
- Ran the full CLI pipeline on synthetic fixtures.
- Ran expected-label evaluation on the matching synthetic control sample.
- No application code or tests were changed because no blocking pipeline, privacy, or test reliability bug was found.

## Result

Done.

## What We Learned

- The fixture pipeline completes end to end and remains privacy-safe by default.
- Metric validation is available on the synthetic control sample and currently passes at 8/8 labels correct.
- The highest-impact hardening gap is confidence calibration: useful messages still enter the review queue at low confidence.

## Next Step

Run the same safe workflow on one explicit private export path, then compare real review noise and missed-cluster patterns against the fixture results.
