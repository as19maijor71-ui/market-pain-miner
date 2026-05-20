# Retrospective: Phase 3 Deduplicated Frequency

Date/time: 2026-05-19 18:04

## Task

Make pain and question frequency honest by counting normalized unique messages
instead of raw copy-paste.

## What Changed

- Added deterministic `normalized_text` for imported messages.
- Stored `normalized_text` in SQLite and backfilled it for older local databases.
- Added active-label frequency stats with `raw_count`, `unique_count`,
  `duplicate_count`, and `weaker_evidence_count`.
- Marked repeated and forwarded messages as weaker evidence in CLI output.
- Added phase 3 tests for exact duplicates, category separation, and forwarded
  evidence.

## Result

Done. `python -m pytest` passes, and the fixture reports the copied pain as
`raw_count=2`, `unique_count=1`, `duplicate_count=1`.

## What We Learned

Exact deduplication is enough for the phase 3 acceptance check, but it should stay
visibly separate from later near-duplicate or cluster logic.

## Next Step

Start phase 4: explicit problem clusters using category, topic, and normalized
problem markers without semantic magic.
