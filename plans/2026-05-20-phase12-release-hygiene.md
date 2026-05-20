# Plan: Phase 12 Release Hygiene

Date: 2026-05-20

## Goal

Prepare the MVP for safe review/commit/PR without expanding product scope:

- describe the accumulated release candidate changes
- verify the privacy boundary before review
- prove the fixture pipeline is reproducible
- keep the real private pilot blocker explicit

## Context

Phases 1-11 are accepted. The real owner-run private pilot remains blocked because the owner-provided export path was not provided.

This phase must not read raw Telegram exports or local database contents. Private paths are checked only through tracked file lists, ignore status, and counts.

`architecture/03-данные/правила-нерушимые.md` was not present in this workspace, so the audit used the repository `AGENTS.md` data rules as the available source of privacy invariants.

## Phases

- [x] Phase 1: Read project operating rules, prompts index, playbooks index, and repo map needed for release hygiene.
- [x] Phase 2: Build a release checklist that separates MVP pipeline, docs/runbooks/plans/retrospectives, and separately reviewable changes.
- [x] Phase 3: Run privacy audit for tracked files and ignored private data paths without reading private data contents.
- [x] Phase 4: Run `python -m pytest` and fixture smoke: import -> classify -> summary -> review -> opportunities.
- [x] Phase 5: Record sanitized release notes and a retrospective.

## Release Checklist

### MVP Pipeline

Candidate files to review as the working CLI MVP:

- `app/cli.py`
- `app/core/models.py`
- `app/importers/telegram.py`
- `app/storage/sqlite.py`
- `app/classifiers/rules.py`
- `app/classifiers/taxonomy.py`
- `app/normalization.py`
- `app/clusters/`
- `app/solutions/`
- `app/opportunities/`
- `app/scoring/`
- `tests/`
- `pyproject.toml`

### Docs, Runbooks, Plans, Retrospectives

Candidate support materials:

- `README.md`
- `CODEX_AUTOPILOT.md`
- `AGENTS.md`
- `plans/`
- `playbooks/`
- `prompts/`
- `skills/`
- `retrospectives/`
- `app/web/README.md`

### Review Separately

Best reviewed in separate passes:

- MVP pipeline code and tests
- project operating assets: `skills/`, `prompts/`, `playbooks/`
- accumulated plans and retrospectives
- `.gitignore` privacy rules
- `app/web/README.md` placeholder, because UI remains intentionally unbuilt

## Privacy Audit

- [x] Tracked status checked.
- [x] Ignored private data status/counts checked for `data/exports` and `data/db` without reading contents.
- [x] Confirmed no tracked `.env` files.
- [x] Confirmed no tracked SQLite/database files.
- [x] Confirmed no tracked raw export files outside synthetic test fixtures.
- [x] Confirmed no unexpected SQLite/database files outside ignored private folders.

Audit summary:

- Tracked files: 35.
- Tracked forbidden private paths: 0.
- Candidate files excluding ignored private data paths: 97.
- Candidate forbidden private paths: 0.
- Ignored private path status entries: 1.
- Private untracked status entries under `data/exports` / `data/db`: 0.
- Private tracked modified entries under `data/exports` / `data/db`: 0.
- `data/exports` file count: 0.
- `data/db` file count: 1.
- Unexpected SQLite/DB files outside `data/db` and `data/exports`: 0.
- Candidate JSON files are synthetic test fixtures under `tests/fixtures/`.
- No `data/exports` or `data/db` contents were read.
- Release-facing import/result command examples use placeholders; generic
  local-only pilot examples remain in playbooks and must be resolved only
  locally.

## Verification

- [x] `python -m pytest` passed: 70 tests after security-review fixes.
- [x] Fixture smoke import passed on synthetic fixture.
- [x] Fixture smoke classify passed on synthetic fixture.
- [x] Fixture smoke summary passed on synthetic fixture.
- [x] Fixture smoke review passed on synthetic fixture.
- [x] Fixture smoke opportunities passed on synthetic fixture.
- [x] Security regression checks covered sanitized importer errors and stricter
  expected-label validation.

## Sanitized Release Notes

### Capabilities

- Telegram Desktop JSON import into local SQLite.
- Deterministic rule-based classification into project categories and marketplace themes.
- CLI reports for stats, summary, clusters, ready solutions, review candidates, and product opportunities.
- Deduplicated frequency reporting with weak evidence flags.
- Evidence-backed opportunity cards with controlled MVP, payment reason, complexity, risk, and score fields.
- Privacy-safe default output using aliases and aggregated fields; raw local output remains explicit opt-in only.
- Project operating assets for repeatable import, pain mining, opportunity building, and pilot hygiene.

### Commands

Verification commands used:

```powershell
python -m pytest
python -m app.cli --db tests/_tmp_phase12_smoke_release.sqlite import tests/fixtures/telegram_solutions_result.json
python -m app.cli --db tests/_tmp_phase12_smoke_release.sqlite classify
python -m app.cli --db tests/_tmp_phase12_smoke_release.sqlite summary --limit 5
python -m app.cli --db tests/_tmp_phase12_smoke_release.sqlite review --limit 5
python -m app.cli --db tests/_tmp_phase12_smoke_release.sqlite opportunities --limit 5
```

Owner-run private pilot command shape remains in `playbooks/06-pilot-runbook.md`; replace placeholders locally and keep resolved private paths out of tracked notes.

### Known Limits

- Real private pilot did not run because no owner-provided export path was given.
- Classifier is deterministic rules only; no LLM, CSV export, FTS, dashboard, or live automation is included in this release candidate.
- Fixtures are synthetic and cannot prove real WB/Ozon slang, screenshots, reply context, or noisy export behavior.
- Review candidates and opportunity cards are research aids, not final product decisions.
- `--raw-local` can expose private data and should stay local-only.

### Remaining Blocker

Real private pilot remains blocked until the owner provides a local Telegram export path.

## Result

Done.

What remains:

- owner review of the release checklist
- separate owner command before any commit/PR
- owner-provided local Telegram export path before the real private pilot

## Orchestrator Review

Accepted.

- Verified with `python -m compileall app tests` and `python -m pytest`: 70
  passed.
- Re-ran fixture smoke on a GUID temp DB:
  `import -> classify -> summary -> review -> opportunities`.
- Reviewed release checklist, privacy audit, and security-review fixes.
- Privacy boundary held: no tracked `data/exports`, `data/db`, `.env`, SQLite
  DBs, raw Telegram data, handles, user IDs, private chat names, or private
  quotes were found in the reviewed tracked/candidate surface.
- Ignored local `data/db/` exists as private storage; contents were not
  inspected.
- Final test count is 70 after security fixes, superseding the earlier 66-test
  hygiene snapshot.
