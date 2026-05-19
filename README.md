# Market Pain Miner for WB/Ozon

Local tool for mining Telegram chats about Wildberries and Ozon, finding repeated market pains, ready solutions, competitor ads, and product opportunities.

## Current Status

This is the initial Codex-oriented project scaffold:

- business context in `.business/`
- project rules in `AGENTS.md`
- onboarding flow in `CODEX_AUTOPILOT.md`
- reusable workflows in `playbooks/`
- implementation plans in `plans/`
- Python MVP skeleton in `app/`

## First MVP

The first version works from Telegram Desktop exports:

1. Export chat history as machine-readable JSON.
2. Import `result.json` into local SQLite.
3. Classify messages into pains, questions, solutions, cases, and insights.
4. Generate reports and product opportunity cards.

## Commands

```powershell
python -m app.cli import "C:\path\to\result.json"
python -m app.cli stats
```

Default database path:

```text
data/db/chatkb.sqlite
```

## Privacy

Raw Telegram exports, local databases, and real business context are private and ignored by git. Public artifacts should be anonymized before sharing.

