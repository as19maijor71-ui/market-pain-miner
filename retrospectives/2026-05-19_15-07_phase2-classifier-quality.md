# Retrospective: Phase 2 Classifier Quality

Date/time: 2026-05-19 15:07

## Task

Make rule-based classification measurable and versioned for the synthetic WB/Ozon
fixture.

## What Changed

- Added versioned classifier label storage with `classifier_name`,
  `classifier_version`, and `run_id`.
- Added a manual expected-label control sample for the synthetic fixture.
- Added `evaluate` to report precision and classification errors.
- Expanded WB/Ozon topic markers for domain terms such as ДРР, СПП, FBO/FBS,
  СЦ, приемка, штрафы, выкупы, карточки, РК, API, остатки, логистика, комиссия.

## Result

Done. `python -m pytest` passes, and the CLI import/classify/evaluate flow reports
1.00 precision for `pain`, `question`, `solution_ad`, and `tool_mention`.

## What We Learned

Classifier versions need to be selected as a whole run in stats/evaluation; mixing
rows from different rule versions would hide quality regressions.

## Next Step

Start deduplication and frequency quality work in phase 3.
