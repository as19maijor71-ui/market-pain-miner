# AGENTS.md - project rules for Codex

## Project

Market Pain Miner for WB/Ozon is a local research tool for finding product opportunities in Telegram chats about Wildberries and Ozon.

The goal is to help build small paid tools, bots, dashboards, and internal apps for sellers, marketplace managers, and agencies by mining real problems, repeated questions, competitor ads, and workaround patterns from chat exports.

## Context Map

Read only the context needed for the task.

| Need | Read |
|---|---|
| Business logic, audience, strategy | `.business/INDEX.md` |
| Marketplace domain | `.business/marketplaces/` |
| Target customers | `.business/audience/` |
| Product and offers | `.business/products/` |
| Pricing and economics | `.business/economics/` |
| Lead generation and positioning | `.business/marketing/` |
| Research rules and privacy | `.business/research/` |
| Implementation plans | `plans/` |
| Session memory | `retrospectives/` |
| Reusable workflows | `playbooks/INDEX.md` |

## Workflow

1. Before business or product decisions, read `.business/INDEX.md` and the specific file that matches the task.
2. Before implementing a non-trivial feature, create or update a plan in `plans/YYYY-MM-DD-name.md`.
3. Keep code changes scoped. Do not refactor unrelated modules.
4. After a meaningful work session, add a short retrospective in `retrospectives/`.
5. For repeatable work, add a playbook instead of relying on memory.

## Data Rules

- Telegram exports are private market research data.
- Never commit `data/exports/`, `data/db/`, `.env`, or real chat participant data.
- Do not publish names, Telegram handles, user IDs, or private quotes without explicit review.
- Store raw messages locally. Public reports should use anonymized snippets or aggregated statistics.
- If a file may contain secrets or personal data, inspect only the minimum needed lines or metadata.

## Product Rules

When extracting an opportunity from chat data, always capture:

- what problem appeared
- who has the problem
- how often it appears
- how people solve it today
- whether someone advertises a ready solution
- first MVP version
- why a seller or manager would pay
- complexity and risk

Default message categories:

- `pain`
- `question`
- `solution_ad`
- `tool_mention`
- `case`
- `insight`
- `offtopic`

Default marketplace themes:

- analytics
- ads
- stock
- cards
- reviews
- prices
- margin
- supply
- penalties
- api
- managers
- automation

## Coding Rules

- Prefer Python stdlib for the first MVP unless a dependency clearly removes real complexity.
- Keep importers deterministic and testable.
- Keep AI/LLM classification behind an interface so we can swap local rules, OpenAI, or manual review later.
- Use SQLite as the first storage layer, with FTS added when search becomes the next priority.
- Make CLI commands work before building complex UI.

## Language

Respond to the user in Russian unless they ask otherwise. Keep implementation notes concise and practical.

