---
name: codex-project-ops
description: "Maintain this Codex project's operating system: read .business context, choose prompts/playbooks, create or update plans, write retrospectives, and keep private data out of git. Use when starting work, planning features, updating project memory, or adapting claude-code-starter style workflows to Codex."
---

# Codex Project Ops

## Workflow

1. Read `AGENTS.md`.
2. For business/product work, read `.business/INDEX.md` and only the specific context files needed.
3. Check `playbooks/INDEX.md` and `prompts/INDEX.md` before inventing a new workflow.
4. For non-trivial implementation, create or update `plans/YYYY-MM-DD-name.md`.
5. Keep `.business/`, `data/exports/`, `data/db/`, and `.env*` out of commits.
6. After a meaningful session, add a concise retrospective in `retrospectives/`.

## Planning Rule

Use `plans/TEMPLATE.md`. Keep the plan short:

- goal
- context
- 3-5 phases
- verification commands
- result

Update checkboxes while working.

## Retrospective Rule

Use `retrospectives/TEMPLATE.md` and capture:

- task
- what changed
- result
- what was learned
- next step

Do not turn retrospectives into long reports.

## Privacy Rule

Never publish or commit raw Telegram exports, real participant handles, user IDs, private quotes, API keys, or local SQLite databases.

## References

Read `references/project-map.md` when the repo structure is unclear.
