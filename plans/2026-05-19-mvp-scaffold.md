# Plan: MVP Scaffold

Date: 2026-05-19

## Goal

Create a Codex-oriented project scaffold for Telegram-based WB/Ozon market pain mining.

## Context

The project adapts the `claude-code-starter` idea to Codex:

- `AGENTS.md` instead of `CLAUDE.md`
- `CODEX_AUTOPILOT.md` instead of `AUTOPILOT.md`
- `.business/` as private project context
- `playbooks/` as reusable workflows
- `plans/` and `retrospectives/` as project memory

## Phases

- [x] Create repository structure.
- [x] Add Codex project rules and onboarding.
- [x] Add WB/Ozon business context.
- [x] Add playbooks and plan templates.
- [x] Add Python import/storage skeleton.
- [x] Verify tree and Python syntax.

## Verification

- [x] `python -m compileall app tests`
- [x] `rg --files`

## Result

Done.

Created the Codex project scaffold, private business context, playbooks, plan templates, and first Python MVP skeleton with Telegram export import into SQLite.
