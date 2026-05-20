# Market Pain Miner for WB/Ozon

Local tool for mining Telegram chats about Wildberries and Ozon, finding repeated market pains, ready solutions, competitor ads, and product opportunities.

## Current Status

This is a local CLI MVP ready for the first owner-run private pilot:

- business context in `.business/`
- project rules in `AGENTS.md`
- onboarding flow in `CODEX_AUTOPILOT.md`
- project-local skills in `skills/`
- copyable prompts in `prompts/`
- reusable workflows in `playbooks/`
- implementation plans in `plans/`
- Python MVP CLI in `app/`

## First MVP

The first version works from Telegram Desktop exports:

1. Export chat history as machine-readable JSON.
2. Import `result.json` into local SQLite.
3. Classify messages into pains, questions, solutions, cases, and insights.
4. Generate reports and product opportunity cards.

## Commands

```powershell
$Export = "<local-result-json-path>"
python -m app.cli import $Export
python -m app.cli stats
```

Default database path:

```text
data/db/chatkb.sqlite
```

## Private Pilot Run

Use the pilot runbook for the first real private export:

- [`playbooks/06-pilot-runbook.md`](./playbooks/06-pilot-runbook.md)

Safe command order:

```powershell
$Export = "data/exports/pilot-001/result.json"
$Db = "data/db/pilot-001.sqlite"

python -m app.cli --db $Db import $Export
python -m app.cli --db $Db classify
python -m app.cli --db $Db summary --limit 10
python -m app.cli --db $Db review --limit 20
python -m app.cli --db $Db opportunities --limit 10
```

Copy or discuss `summary` first. Do not copy raw Telegram output, private chat names, participant names, Telegram handles, user IDs, URLs, or raw quotes into tracked files or public notes.

Use `--raw-local` only for local debugging on your own machine. Commands with raw mode can expose authors, previews, raw chat IDs, normalized evidence text, URLs, handles, or raw evidence IDs.

## Skills And Prompts

Project-local Codex skills:

- `skills/codex-project-ops`
- `skills/telegram-market-import`
- `skills/wb-ozon-pain-mining`
- `skills/product-opportunity-builder`

Prompt library:

- `prompts/INDEX.md`

These are stored in the project so they can evolve with the product. For automatic Codex discovery, install/copy the skill folders into `$CODEX_HOME/skills` or `~/.codex/skills`.

## Privacy

Raw Telegram exports, local databases, and real business context are private and ignored by git. Public artifacts should be anonymized before sharing.

Before finishing a pilot session, use the cleanup checklist in the pilot runbook. Do not rely on `git status --short` alone: exports, DBs, `.env`, and SQLite files are ignored by git, so they can exist locally while normal status output stays silent.

At minimum, check both tracked changes and ignored private paths:

```powershell
git status --short
git status --short --ignored data/exports data/db
```

The full cleanup checklist prints counts instead of full local paths; keep any detailed local file listings out of tracked files and public notes.
