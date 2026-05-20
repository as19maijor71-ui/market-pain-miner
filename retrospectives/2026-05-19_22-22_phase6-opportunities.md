# Retrospective: Phase 6 Opportunity Cards

Date/time: 2026-05-19 22:22

## Task

Build evidence-backed opportunity cards for Market Pain Miner without reading
real exports or private DBs.

## What Changed

- Added `app.opportunities` with `OpportunityCard`, field-level evidence, and
  deterministic scoring.
- Added `python -m app.cli opportunities` with safe evidence aliases by default.
- Added phase 6 tests for unknown fields, ad-only payment safety, unique-count
  scoring, privacy-safe output, and score ordering.

## Result

Done. `python -m pytest` passes, and the CLI chain
`import -> classify -> opportunities` works on the synthetic solutions fixture.

## What We Learned

Solution ads are useful as competitor evidence, but payment evidence has to come
from trust/payment signals, time or money loss, repeated workflows, or manager /
agency context. Keeping card values as controlled labels makes privacy checks
much easier.

## Next Step

Start phase 7: show low-confidence labels and disputed clusters only where they
can improve a card or a quality metric.
