# Plan: Project Skills And Prompts

Date: 2026-05-19

## Goal

Add project-local Codex skills and a prompt library so the WB/Ozon research workflow is reusable, not only described in prose.

## Context

The initial scaffold had `playbooks/`, but was missing actual skill packages and copyable prompts similar to the starter repository's prompt library.

## Phases

- [x] Create project-local skills in `skills/`.
- [x] Add references/assets where useful.
- [x] Add copyable prompts in `prompts/`.
- [x] Update `AGENTS.md`, `README.md`, and `CODEX_AUTOPILOT.md`.
- [x] Validate skill folders.

## Verification

- [x] `quick_validate.py skills/codex-project-ops`
- [x] `quick_validate.py skills/telegram-market-import`
- [x] `quick_validate.py skills/wb-ozon-pain-mining`
- [x] `quick_validate.py skills/product-opportunity-builder`
- [x] `python -m unittest discover -s tests`

## Result

Done.

