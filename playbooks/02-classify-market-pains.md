# Playbook: Classify Market Pains

## Goal

Turn raw messages into useful market intelligence.

## Categories

- `pain`: direct complaint, frustration, loss, manual work, recurring blocker.
- `question`: user asks how to solve a marketplace problem.
- `solution_ad`: someone promotes a bot, service, site, table, course, or app.
- `tool_mention`: neutral mention of a tool or service.
- `case`: concrete story, result, experiment, or business example.
- `insight`: practical observation, rule, warning, or pattern.
- `offtopic`: greetings, jokes, logistics, unrelated messages.

## Topic Tags

Use `.business/marketplaces/pain-taxonomy.md`.

## Evidence Rule

Every useful classification should keep source message IDs. No evidence, no product conclusion.

## Batch Rule

For large exports, process in batches and save progress. Do not rely on one huge context window.

