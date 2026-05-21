# Plan: Codex Project Architecture

Date: 2026-05-21

## Goal

Create a practical architecture document for Market Pain Miner, adapted from the Claude Code Starter style to the current Codex workflow and existing Python MVP.

## Context

- Local operating system already exists: `AGENTS.md`, `CODEX_AUTOPILOT.md`, `.business/`, `skills/`, `prompts/`, `playbooks/`, `plans/`, `retrospectives/`.
- External reference: `artemiimillier/claude-code-starter`, especially the README structure: business context, agent rules, autopilot, prompts, plans, retrospectives, templates, and safety.
- Product code is a local-first Python CLI with Telegram JSON import, SQLite storage, rule-based classification, clusters, solution extraction, opportunity cards, review, and summary commands.

## Phases

- [x] Phase 1: Read local project map, business index, workflows, and core app modules.
- [x] Phase 2: Read the starter repository README and extract concepts worth adapting to Codex.
- [x] Phase 3: Write architecture document for operating system, data pipeline, module boundaries, privacy, and evolution.
- [x] Phase 4: Link architecture from project docs and capture a retrospective.

## Verification

- [x] Command/test: inspect repository files without reading private exports or databases.
- [x] Manual check: architecture maps current files and future direction without exposing private data.

## Result

Done.

What remains:

- Add a small security audit script later if this becomes a repeated release workflow.
- Split the large CLI into command modules when the next feature makes that refactor worth it.
