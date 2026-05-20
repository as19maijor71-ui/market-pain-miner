# Plan: Phase 7 Manual Review Loop

Date: 2026-05-19

## Goal

Add a minimal CLI review cycle that stores manual corrections separately and lets `evaluate` and `opportunities` show their impact without exposing private raw data by default.

## Context

Relevant files:

- `app/cli.py`
- `app/storage/sqlite.py`
- `app/core/models.py`
- `app/opportunities/rules.py`
- `tests/`

Constraints:

- Do not read or commit `data/exports/`, `data/db/`, `.env`, or real participant data.
- Manual labels must use `source=manual` and transparent classifier metadata.
- Default output must stay privacy-safe; raw local detail only through explicit `--raw-local`.

## Phases

- [x] Phase 1: Inspect current CLI/storage/evaluation flow.
- [x] Phase 2: Add review candidate listing and manual label corrections.
- [x] Phase 3: Make `evaluate` report effective manual impact.
- [x] Phase 4: Add focused synthetic tests for metric/card impact and privacy.

## Verification

- [x] Command/test: `python -m pytest`
- [x] Manual check: fixture flow `import -> classify -> review -> evaluate -> opportunities`

## Result

Done.

What remains:

- Nothing for phase 7 scope.
