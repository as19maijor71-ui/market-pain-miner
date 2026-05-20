# Plan: Phase 8 Local Research Run

Date: 2026-05-20

## Goal

Validate the post-MVP CLI pipeline end to end on safe local data, surface the highest-impact MVP gaps before dashboard/CSV/FTS, and keep private Telegram data out of tracked outputs.

## Context

- Phases 1-7 are accepted.
- Pipeline commands: `import -> classify -> stats -> evaluate -> clusters -> solutions -> opportunities -> review`.
- No private Telegram export path was provided for this session.
- Actual run uses synthetic fixtures in `tests/fixtures/`.
- Private data rules: do not commit `data/exports/`, `data/db/`, `.env`, real names, handles, user IDs, raw quotes, private chat names, or raw Telegram data.

## Safe Local Runbook

For a private local export, run with a fresh local ignored DB path and keep default safe output:

```powershell
$runId = "$(Get-Date -Format yyyyMMdd-HHmmss)-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$export = "C:\private\path\to\result.json"
$db = "data/db/phase8-$runId.sqlite"
$expected = "C:\private\path\to\matching-expected-labels.json"

python -m app.cli --db $db import $export
python -m app.cli --db $db classify
python -m app.cli --db $db stats
python -m app.cli --db $db clusters
python -m app.cli --db $db solutions
python -m app.cli --db $db opportunities --limit 5
python -m app.cli --db $db review

if (Test-Path -LiteralPath $expected) {
    python -m app.cli --db $db evaluate --expected $expected
} else {
    Write-Output "metric validation unavailable for this run"
}
```

Only set `$expected` to a matching local expected-labels JSON for this exact export/chat set. If no matching expected-labels file exists, leave the placeholder as-is and record: `metric validation unavailable for this run`.

Use `--raw-local` only for private terminal debugging, never for committed reports or copied summaries.

## Phases

- [x] Phase 1: Read project context, local skills, prompts, playbooks, and privacy rules.
- [x] Phase 2: Run fixture pipeline end to end and capture sanitized output.
- [x] Phase 3: Run expected-label evaluation if the local sample exists.
- [x] Phase 4: Fix only blocking pipeline, privacy, or test reliability bugs found by the run.
- [x] Phase 5: Write sanitized run summary, next gaps, and retrospective.

## Verification

- [x] Command/test: fixture pipeline completes.
- [x] Command/test: expected-label evaluation completes.
- [x] Command/test: `python -m pytest`.
- [x] Manual check: `git status --short` contains no `data/exports`, `data/db`, `.env`, or raw Telegram data.
- [x] Manual check: summary contains only sanitized aliases, aggregate counts, and generalized findings.

## Commands Run

```powershell
python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite import tests/fixtures/telegram_solutions_result.json
python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite classify
python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite stats
python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite clusters
python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite solutions
python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite opportunities --limit 5
python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite review
python -m app.cli --db tests/_tmp_phase8_eval.sqlite import tests/fixtures/telegram_result.json
python -m app.cli --db tests/_tmp_phase8_eval.sqlite classify
python -m app.cli --db tests/_tmp_phase8_eval.sqlite evaluate --expected tests/fixtures/telegram_expected_labels.json
python -m pytest
git status --short
```

Temporary SQLite files were removed after the run.

## Sanitized Run Summary

Private export path was not provided, so this phase used synthetic fixtures only.

### Pipeline Counts

- Import/classify smoke fixture: 1 chat, 9 messages, 9 labels, 0 unclassified.
- Active label distribution: `pain=3`, `solution_ad=3`, `tool_mention=2`, `offtopic=1`.
- Deduplicated key frequencies: `pain unique=3`, `solution_ad unique=3`, `tool_mention unique=2`.
- Clusters: 1 supported cluster, 0 weak clusters.
- Solutions: 3 sanitized solution records.
- Opportunities: 1 card.
- Review candidates: 6 low-confidence/disputed labels, 3 disputed/noise cases, 0 opportunity cards needing review.

### Metric Validation

Local expected-labels sample exists and was run on its matching synthetic fixture.

- Control sample: 8 messages.
- Result: 8/8 labels correct.
- Macro precision: 1.00.
- Errors: 0.

### Top Opportunity Cards

1. `opportunity1`: stock reconciliation checker.
   - Score: 27, verdict `promising`.
   - Problem: stock reconciliation mismatch.
   - Segment: marketplace managers and sellers.
   - Evidence strength: supported cluster with 3 unique pain messages and no weak evidence.
   - Ready-solution signal: one trusted bot-like solution record plus one ad-only analytics-service record.
   - MVP: stock reconciliation checker.
   - Main risk: marketplace data quality and export/API changes.

### Review Candidates

- Low-confidence review queue is dominated by useful marketplace messages at `0.55` confidence.
- Noise cases are solution/tool mentions that match the same stock reconciliation marker but should not enter pain frequency.
- No weak-signal clusters or opportunity cards were flagged for review in the smoke fixture.

### Quality Gaps

1. Quality: confidence calibration is too conservative for fixture pains and tool mentions, creating review noise even when categories are correct.
2. Quality: semantic coverage is narrow around explicit problem markers; real exports may contain weaker wording that forms no cluster.
3. Privacy: default outputs are safe, but `--raw-local` remains a sharp local-only option and should stay out of copied summaries.
4. UX: run output is terminal-only; a researcher must manually copy counts and cards into a summary.
5. Performance: no issue at fixture scale; large private exports still need timing and batching observations.

### Privacy Notes

- No private Telegram export was read.
- No `data/exports`, `data/db`, `.env`, raw handles, raw user IDs, private chat names, or raw long quotes were added to git status.
- Summary uses aggregate counts, controlled labels, and sanitized aliases only.

## Result

Done.

## Orchestrator Review

Accepted.

- Verified with `python -m compileall app tests` and `python -m pytest`.
- Re-ran fixture pipeline:
  `import -> classify -> stats -> clusters -> solutions -> opportunities -> review`.
- Re-ran matching synthetic evaluation:
  `import -> classify -> evaluate --expected tests/fixtures/telegram_expected_labels.json`.
- Privacy check passed: no `data/exports`, `data/db`, `.env`, real Telegram data,
  raw handles/user IDs, private chat names, or long raw quotes were added to git
  status or sanitized summaries.
- Scope check passed: no application/test changes were needed for phase 8 because
  no blocking pipeline, privacy, or test reliability bug was found.

What remains:

- Run the same workflow on one explicit private local export path when provided by the project owner.
- Keep the next iteration focused on quality calibration, privacy-safe summaries, and real-export performance observations before dashboard/CSV/FTS.
