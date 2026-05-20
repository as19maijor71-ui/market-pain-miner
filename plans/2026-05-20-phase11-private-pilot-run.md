# Plan: Phase 11 Private Pilot Run

Date: 2026-05-20

## Goal

Execute the first owner-provided private pilot safely, or prepare the sanitized findings structure when no explicit local Telegram export path is provided.

## Context

- Phases 1-10 are accepted.
- Safe pilot runbook exists at `playbooks/06-pilot-runbook.md`.
- CLI is ready for `import -> classify -> summary -> review -> opportunities`.
- No owner-provided local Telegram export path was provided in this phase 11 request.
- Private pilot commands must not run without an explicit local export path.
- Privacy rules remain strict: do not commit or paste `data/exports`, `data/db`, `.env`, SQLite DBs, raw Telegram data, real names, handles, user IDs, private chat names, or raw quotes.

## Phases

- [x] Phase 1: Read the project pilot runbook and project-ops workflow.
- [x] Phase 2: Determine whether an explicit owner-provided local export path exists.
- [x] Phase 3: Record blocked state and prepare a sanitized findings template only.
- [x] Phase 4: Run fixture smoke and `python -m pytest`.
- [x] Phase 5: Check privacy status and add retrospective.

## Verification

- [x] Command/test: fixture smoke `import -> classify -> summary -> review -> opportunities` on synthetic fixture only.
- [x] Command/test: `python -m pytest`.
- [x] Manual check: no tracked `data/exports`, `data/db`, `.env`, SQLite DBs, or raw Telegram data.
- [x] Manual check: plan and retrospective contain no raw names, handles, user IDs, private chat names, or raw quotes.

## Pilot Status

Blocked on owner-provided local export path.

The private pilot was not executed. No real Telegram export was read, imported, classified, summarized, reviewed, or converted into opportunities.

## Sanitized Findings Template

Use this section only after the owner provides an explicit local Telegram Desktop JSON export path and the safe runbook commands complete.

### Run Metadata

- Pilot input: not provided in this phase.
- Private data access: not performed.
- Private DB created: no.
- Raw CLI output stored in tracked docs: no.
- Raw local mode used: no.

### Counts

- Chats imported: blocked, not measured.
- Messages imported: blocked, not measured.
- Messages classified: blocked, not measured.
- Unclassified messages: blocked, not measured.
- Category counts: blocked, not measured.
- Theme counts: blocked, not measured.
- Clusters found: blocked, not measured.
- Opportunities found: blocked, not measured.
- Review candidates: blocked, not measured.

### Top Opportunities

No real top opportunities recorded because the private pilot did not run.

When unblocked, record only sanitized opportunity cards:

- Opportunity:
- Problem:
- Audience:
- Frequency signal:
- Current workaround:
- Ready-solution/competitor signal:
- First MVP:
- Why someone pays:
- Complexity:
- Risk:
- Evidence shape: aggregated only, no raw quotes or identities.

### Review Noise

Not measured because the private pilot did not run.

When unblocked, record:

- Count of review candidates:
- Main noise reasons:
- Correct labels that still looked weak:
- Ads/tool mentions needing manual review:
- Safe examples: use paraphrases or aggregate patterns only.

### Missed Or Weak Patterns

Not measured because the private pilot did not run.

When unblocked, record:

- Marketplace slang the rules missed:
- Ambiguous questions/pains:
- Screenshot, reply-context, or media-dependent cases:
- Weak clusters with too little support:
- Opportunities that need owner review before promotion:

### Privacy Notes

- No private Telegram export path was provided.
- No private export was read.
- No raw command output was saved to tracked docs.
- No real names, handles, user IDs, private chat names, or raw quotes were recorded.
- Any future private pilot findings must stay aggregated, paraphrased, or anonymized.

### Performance Notes

Not measured because the private pilot did not run.

When unblocked, record:

- Import runtime:
- Classification runtime:
- Summary runtime:
- Review runtime:
- Opportunities runtime:
- Any terminal-output volume or memory issues:

### Next Quality Gaps

- Need an explicit owner-provided local export path before the real pilot can start.
- Need first private summary to see category/theme distribution outside fixtures.
- Need first private review pass to identify real slang, ambiguous ads, weak evidence, and missed marketplace patterns.
- Need owner review before changing taxonomy or confidence rules based on private data.

## Verification Results

- Fixture smoke on synthetic data passed through `import -> classify -> summary -> review -> opportunities`.
- `python -m pytest` passed: 66 tests.
- Temporary fixture-smoke SQLite DB was removed after verification.
- Tracked forbidden private files: 0.
- Tracked SQLite/DB files from hygiene check: 0.
- `.env` files present: 0.
- Unexpected SQLite/DB files outside ignored private folders: 0.
- Ignored private folders were checked locally; exact counts, paths, contents, and file identities are not recorded in tracked docs.
- Security follow-up: repeatable fixture smoke recipe was updated to use a GUID DB path, fail fast on native command errors, and was syntax-checked on the synthetic fixture without keeping the temporary DB.

## Commands Run

These are the actual one-off verification commands from this phase:

```powershell
python -m app.cli --db tests/_tmp_phase11_smoke.sqlite import tests/fixtures/telegram_solutions_result.json
python -m app.cli --db tests/_tmp_phase11_smoke.sqlite classify
python -m app.cli --db tests/_tmp_phase11_smoke.sqlite summary --limit 3
python -m app.cli --db tests/_tmp_phase11_smoke.sqlite review --limit 3
python -m app.cli --db tests/_tmp_phase11_smoke.sqlite opportunities --limit 3
python -m pytest
```

## Repeatable Fixture Smoke Recipe

Use a unique smoke DB path for any rerun so parallel sessions cannot share, delete, or lock the same SQLite file. Stop on the first failed command so a later successful command cannot mask a broken smoke run.

```powershell
$RunId = [guid]::NewGuid().ToString("N")
$Db = "tests/_tmp_phase11_smoke_$RunId.sqlite"

function Invoke-SmokeStep {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][scriptblock]$Command
  )

  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "Smoke step failed: $Name exit=$LASTEXITCODE"
  }
}

try {
  Invoke-SmokeStep "import" { python -m app.cli --db $Db import tests/fixtures/telegram_solutions_result.json }
  Invoke-SmokeStep "classify" { python -m app.cli --db $Db classify }
  Invoke-SmokeStep "summary" { python -m app.cli --db $Db summary --limit 3 }
  Invoke-SmokeStep "review" { python -m app.cli --db $Db review --limit 3 }
  Invoke-SmokeStep "opportunities" { python -m app.cli --db $Db opportunities --limit 3 }
}
finally {
  foreach ($Suffix in @("", "-wal", "-shm", "-journal")) {
    $Path = "$Db$Suffix"
    if (Test-Path -LiteralPath $Path) {
      Remove-Item -LiteralPath $Path
    }
  }
}
```

## Result

Blocked for real private pilot. Sanitized findings template prepared and synthetic fixture verification passed.

## Orchestrator Review

Accepted as safe fallback.

- Verified with `python -m compileall app tests` and `python -m pytest`.
- Re-ran fixture smoke with a GUID temp DB through
  `import -> classify -> summary -> review -> opportunities`.
- Acceptance matched: no explicit owner-provided local export path was present,
  so the real private pilot was not executed and the phase records a blocked
  state plus a sanitized findings template.
- Privacy check passed for tracked files: no real export, raw Telegram data,
  `.env`, SQLite DB, names, handles, user IDs, private chat names, or raw quotes
  were added. Local ignored `data/db/` exists but was not inspected.

What remains:

- Owner provides an explicit local Telegram export path.
- Runner executes the safe runbook locally and records only sanitized aggregate findings.
