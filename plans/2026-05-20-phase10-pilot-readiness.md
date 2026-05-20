# Plan: Phase 10 Pilot Readiness

Date: 2026-05-20

## Goal

Prepare the accepted MVP for the first owner-run private pilot without expanding the product surface.

## Context

- Phases 1-9 are accepted.
- The CLI supports `import`, `classify`, `stats`, `evaluate`, `clusters`, `solutions`, `opportunities`, `review`, and `summary`.
- Phase 9 reduced review noise and added privacy-safe `summary`.
- No real private export path was provided in this session, so phase 10 uses synthetic fixtures only.
- Privacy rules remain strict: do not read or commit `data/exports/`, `data/db/`, `.env`, real participant names, handles, user IDs, private chat names, raw quotes, or raw Telegram data.
- Scope is release hygiene only: no dashboard/UI, LLM, CSV, FTS, live Telegram automation, taxonomy changes, or confidence changes.

## Phases

- [x] Phase 1: Verify current CLI help and privacy/UX errors for DB paths, `--raw-local`, `--allow-external-db`, expected labels, and manual categories.
- [x] Phase 2: Add a safe owner pilot runbook for `import -> classify -> summary -> review -> opportunities`.
- [x] Phase 3: Add a pilot checklist for export/db storage, raw output handling, `--raw-local`, cleanup, and remaining pilot risks.
- [x] Phase 4: Run fixture smoke pipeline through `summary`, plus `review` and `opportunities` as release-readiness checks.
- [x] Phase 5: Run `python -m pytest`, check git privacy status, and add retrospective.

## Verification

- [x] Command/test: `python -m app.cli --help`
- [x] Command/test: `python -m app.cli summary --help`
- [x] Command/test: `python -m app.cli review --help`
- [x] Command/test: `python -m app.cli opportunities --help`
- [x] Command/test: `python -m app.cli stats --help`
- [x] Command/test: `python -m app.cli evaluate --help`
- [x] Command/test: `python -m app.cli --db tmp_phase10_probe.sqlite stats`
- [x] Command/test: `python -m app.cli --db tmp_phase10_external.sqlite --allow-external-db stats`
- [x] Command/test: `python -m app.cli --db tests/_tmp_phase10_expected.sqlite evaluate --expected data/db/private-labels.json`
- [x] Command/test: `python -m app.cli --db tests/_tmp_phase10_expected.sqlite evaluate --expected README.md`
- [x] Command/test: `python -m app.cli --db tests/_tmp_phase10_expected.sqlite review --set-label chat1:1 invalid_category`
- [x] Command/test: fixture smoke pipeline through `summary`
- [x] Command/test: fixture smoke checks for `review` and `opportunities`
- [x] Command/test: `python -m pytest`
- [x] Manual check: README/runbook contains a safe private pilot flow without raw data.
- [x] Manual check: `git status --short` contains no `data/exports`, `data/db`, `.env`, temporary SQLite DBs, or raw Telegram data from this phase.

## CLI Readiness Notes

- Top-level help documents `--db` and `--allow-external-db`.
- `summary` has no `--raw-local` mode and stays privacy-safe by default.
- `stats`, `clusters`, `solutions`, `review`, and `opportunities` expose `--raw-local` with explicit unsafe local-only help text.
- External SQLite-like DB paths are rejected by default unless they are under `data/db/`, are test temp DBs under `tests/_tmp*.sqlite`, or `--allow-external-db` is passed.
- Expected labels refuse private Telegram data paths and non-JSON paths.
- Manual review categories are constrained to `pain`, `question`, `solution_ad`, `tool_mention`, `case`, `insight`, and `offtopic`.

## Commands Run

```powershell
python -m app.cli --help
python -m app.cli import --help
python -m app.cli classify --help
python -m app.cli stats --help
python -m app.cli evaluate --help
python -m app.cli clusters --help
python -m app.cli solutions --help
python -m app.cli summary --help
python -m app.cli review --help
python -m app.cli opportunities --help
python -m app.cli --db tmp_phase10_probe.sqlite stats
python -m app.cli --db tmp_phase10_external.sqlite --allow-external-db stats
python -m app.cli --db tests/_tmp_phase10_expected.sqlite evaluate --expected data/db/private-labels.json
python -m app.cli --db tests/_tmp_phase10_expected.sqlite evaluate --expected README.md
python -m app.cli --db tests/_tmp_phase10_expected.sqlite review --set-label chat1:1 invalid_category
python -m app.cli --db tests/_tmp_phase10_smoke.sqlite import tests/fixtures/telegram_solutions_result.json
python -m app.cli --db tests/_tmp_phase10_smoke.sqlite classify
python -m app.cli --db tests/_tmp_phase10_smoke.sqlite summary --limit 3
python -m app.cli --db tests/_tmp_phase10_smoke.sqlite review --limit 3
python -m app.cli --db tests/_tmp_phase10_smoke.sqlite opportunities --limit 3
python -m pytest
git status --short
```

Temporary phase 10 SQLite files were removed after verification. Two stale ignored `tests/_tmp*.sqlite` files from older runs were also removed without reading their contents.

## Post-Review Fixes

- Replaced `git status --short` as the only privacy check with explicit ignored-path and filesystem scans.
- Changed export cleanup from deleting only `result.json` to deleting the whole checked pilot export folder, so Telegram media/file subfolders do not remain.
- Documented that `chatN:msg_id` aliases are valid only for the latest `review` output on the current DB before another import.
- Removed the misleading real-pilot `evaluate` example that pointed at synthetic fixture expected labels.
- Security follow-up: changed cleanup scans to print counts instead of full local paths, and made export-folder deletion a preview-plus-confirmation flow.

## Remaining Pilot Risks

- Quality: deterministic rules may miss real seller wording, slang, screenshots, voice-note context, or marketplace-specific edge cases not present in fixtures.
- Privacy: `--raw-local` can print private authors, previews, raw chat IDs, URLs, handles, and evidence text; use it only for local debugging and never paste raw output into tracked files or public reports.
- Performance: the first real export may be much larger than fixtures; SQLite/rule-based commands are expected to be acceptable for MVP, but runtime and terminal output volume are untested on a private full chat.
- Operator workflow: the owner still needs to choose export location, DB naming, cleanup discipline, and which `review` findings are worth manual correction.

## Result

Done.

## Orchestrator Review

Accepted.

- Verified with `python -m compileall app tests` and `python -m pytest`.
- Re-ran CLI help checks for the main pilot commands.
- Re-ran guardrail checks: external SQLite-like DB paths are rejected by default,
  `--allow-external-db` works for explicit local-only DBs, private expected-label
  paths and non-JSON expected labels are rejected, and invalid manual categories
  are rejected.
- Re-ran fixture smoke:
  `import -> classify -> summary -> review -> opportunities`.
- Acceptance matched: README and `playbooks/06-pilot-runbook.md` document a safe
  owner pilot flow, cleanup discipline, raw-local risks, expected-label limits,
  manual review constraints, and remaining pilot risks.
- Privacy check passed for tracked changes: no real exports, raw Telegram data,
  `.env`, or temporary phase 10 SQLite files were added. `data/db/` exists only
  as an ignored local private-storage path and its contents were not inspected.

What remains:

- Owner runs the documented pilot on one explicit private local export path and records sanitized findings only.
