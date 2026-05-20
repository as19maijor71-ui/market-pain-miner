# Plan: Phase 4 Explicit Clusters

Date: 2026-05-19

## Goal

Add deterministic pain/question clusters built from explicit category, topic, problem marker, and normalized evidence.

## Context

- Use only synthetic fixtures under `tests/fixtures/`.
- Do not read `data/exports/`, `data/db/`, `.env`, or real participant data.
- Keep clustering explainable: no LLM, fuzzy matching, embeddings, opportunity cards, or UI.
- Existing pipeline already imports Telegram exports, stores normalized text, classifies messages, and reports deduplicated frequencies.

## Phases

- [x] Phase 1: Inspect current CLI, classifier, storage, and tests.
- [x] Phase 2: Add explicit problem marker dictionary and cluster model.
- [x] Phase 3: Implement cluster query/building and `python -m app.cli clusters`.
- [x] Phase 4: Add synthetic fixture coverage for supported, weak, duplicates, weak evidence, and rejected noise.
- [x] Phase 5: Verify tests and CLI scenario.

## Verification

- [x] Command/test: `python -m pytest`
- [x] CLI: `python -m app.cli --db tests\_tmp_phase4_cli.sqlite import tests\fixtures\telegram_clusters_result.json`
- [x] CLI: `python -m app.cli --db tests\_tmp_phase4_cli.sqlite classify`
- [x] CLI: `python -m app.cli --db tests\_tmp_phase4_cli.sqlite clusters`

## Result

Done.

What remains:

- Future phases can add richer opportunity scoring/cards on top of these explicit clusters.
