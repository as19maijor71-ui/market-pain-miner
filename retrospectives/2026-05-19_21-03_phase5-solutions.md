# Retrospective: Phase 5 Solution Mentions

Date/time: 2026-05-19 21:03

## Task

Add a separate privacy-safe solution/competitor report without mixing ads and
tool mentions into pain evidence.

## What Changed

- Added deterministic `app.solutions` extraction and `python -m app.cli solutions`.
- Added synthetic `telegram_solutions_result.json` with ads, tool mentions,
  recommendations, affiliate/spam, pricing, subscription, and alternative complaints.
- Added tests for extraction fields, safe output, and separation from pain clusters.

## Result

Done. `python -m pytest` passes, and the CLI scenario works on the synthetic fixture.

## What We Learned

Ads need their own payment status. A plain solution ad is competitor context, but
not willingness-to-pay evidence unless price, subscription, recommendation,
repeat mention, or alternative complaint signals are present.

## Next Step

Use these solution records as a supporting input for phase 6 opportunity cards,
without letting them overwrite the pain evidence.

## Correction

Follow-up review found and fixed trust/privacy edge cases: repeated independent
mentions now require distinct sources, ad prices are not payment evidence by
themselves, default promises are controlled labels instead of raw snippets, and
over-broad solution markers were narrowed.
