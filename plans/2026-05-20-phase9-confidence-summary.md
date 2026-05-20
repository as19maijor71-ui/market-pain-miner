# Plan: Phase 9 Confidence Summary

Date: 2026-05-20

## Goal

Reduce review noise after the first safe run by calibrating confidence only for proven deterministic rule cases, and add one privacy-safe CLI summary for a research run.

## Context

- Phases 1-8 are accepted.
- Phase 8 fixture pipeline works, but review is noisy because correct rule-based pains and tool mentions sit at the review threshold.
- No private Telegram export path was provided for this session.
- Privacy rules: do not read or commit `data/exports/`, `data/db/`, `.env`, real names, handles, user IDs, private chat names, raw quotes, or raw Telegram data.
- Scope is hardening only: no dashboard/UI, LLM, CSV, FTS, live automation, or broad taxonomy changes.

## Phases

- [x] Phase 1: Add targeted confidence calibration for deterministic `pain` and `tool_mention` cases already covered by fixtures.
- [x] Phase 2: Add tests proving correct fixture pains/tool mentions leave review for confidence reasons while weak/offtopic/ambiguous cases remain review candidates.
- [x] Phase 3: Add `python -m app.cli summary` with privacy-safe counts, clusters, solutions, opportunities, review candidates, and quality gaps.
- [x] Phase 4: Verify pytest, fixture pipeline, safe summary output, and git privacy status.
- [x] Phase 5: Add retrospective and record phase result.

## Verification

- [x] Command/test: `python -m pytest`
- [x] Command/test: fixture pipeline completes.
- [x] Command/test: `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite summary`
- [x] Manual check: `review` is less noisy on known correct cases without hiding weak signals.
- [x] Manual check: `git status --short` contains no `data/exports`, `data/db`, `.env`, or temporary SQLite DBs added by this phase.

## Commands Run

```powershell
python -m pytest tests/test_phase9_confidence_summary.py
python -m pytest
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite import tests/fixtures/telegram_solutions_result.json
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite classify
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite stats
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite clusters
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite solutions
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite opportunities --limit 5
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite review
python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite summary
python -m app.cli --db tests/_tmp_phase9_eval.sqlite import tests/fixtures/telegram_result.json
python -m app.cli --db tests/_tmp_phase9_eval.sqlite classify
python -m app.cli --db tests/_tmp_phase9_eval.sqlite evaluate --expected tests/fixtures/telegram_expected_labels.json
python -m app.cli --db tests/_tmp_phase9_eval.sqlite review
python -m app.cli --db tests/_tmp_phase9_eval.sqlite summary
git status --short
```

Temporary phase 9 SQLite files were removed after the run.

## Sanitized Run Summary

Private export path was not provided, so phase 9 used synthetic fixtures only.

### Confidence Calibration

- Classifier version: `2026-05-20.1`.
- Raised confidence only for deterministic rule branches:
  - `tool_mention` with explicit locator plus controlled tool marker.
  - `pain` with marketplace topic plus strong pain marker such as broken workflow, manual work, loss, error, or penalty wording.
- Kept weaker branches at reviewable confidence:
  - questions remain `0.50`.
  - weak/ambiguous pains remain `0.55`.
  - case/insight/offtopic remain reviewable when weak or topic-disputed.

### Review Noise

- On the synthetic solutions fixture, low-confidence/disputed label candidates dropped to 1.
- Correct fixture pains and tool mentions no longer appear only because of low confidence.
- Disputed/noise cases remain visible when solution/tool mentions match a problem marker but should not enter pain frequency.

### Summary CLI

- Added `python -m app.cli summary`.
- Default output includes aggregate counts, category distribution, deduplicated frequencies, top clusters, sanitized solutions, top opportunities, review candidate counts, and quality gaps.
- Default output uses chat aliases and solution/locator aliases; it does not print raw URLs, handles, authors, user IDs, private chat names, or raw quotes.

### Metric Validation

- Matching expected-label fixture remains green:
  - 8/8 labels correct.
  - Macro precision: 1.00.
  - Errors: 0.

### Privacy Notes

- No private Telegram export was read.
- No `data/exports`, `data/db`, `.env`, real Telegram data, raw handles/user IDs, private chat names, or temporary phase 9 SQLite files were added to git status.

### Post-Review Fixes

- Tightened high-confidence `tool_mention` calibration so locator-based tool mentions need detected marketplace topics to leave low-confidence review.
- Removed bare `вручную` as a sufficient high-confidence pain marker; manual-work messages now need concrete pain context such as time loss, repeated workflow, mismatch, or loss wording.
- Wrapped `summary` reads in one SQLite read transaction so the report uses a stable snapshot when another classifier run appears mid-read.
- Added regression tests for ambiguous URL/manual-work review candidates and summary snapshot consistency.

## Result

Done.

## Orchestrator Review

Accepted.

- Verified with `python -m compileall app tests`, `python -m pytest`, and
  `python -m pytest tests/test_phase9_confidence_summary.py -q`.
- Re-ran fixture pipeline through `review` and `summary`.
- Re-ran matching synthetic evaluation through `evaluate`, `review`, and
  `summary`.
- Acceptance matched: known deterministic pain/tool cases leave low-confidence
  review, weak/offtopic/ambiguous cases remain visible, evaluate stays at 8/8
  with macro precision 1.00, and `summary` gives one privacy-safe research
  report.
- Privacy check passed: no `data/exports`, `data/db`, `.env`, real Telegram
  data, raw handles/user IDs, private chat names, or temporary phase 9 SQLite
  files were added to git status.

What remains:

- Run the calibrated summary on one explicit private local export path when provided by the project owner.
