# Playbook: Competitor And Ready Solution Scan

## Goal

Extract ready solutions from Telegram chats and turn them into competitor intelligence.

## Signals

- Bot or service announcement.
- Link to a landing page.
- Screenshot or demo.
- Pricing mention.
- "I made a tool for..."
- "Use this service..."
- Repeated recommendation of the same product.

## Fields

- name
- type
- locator alias (`url1`, `handle1`, or `none` in tracked/public notes)
- target user
- promise
- features
- pricing
- source message IDs
- visible weakness

Keep raw links, Telegram handles, and authors local-only. Do not copy them into
tracked plans, retrospectives, README, issues, PRs, public reports, or chat
messages. If a raw locator is needed for debugging, use the private local DB or
rerun a raw-local command and summarize with aliases afterward.

## Output

Competitor entry plus possible opportunity:

> What can we build simpler, narrower, faster, or more adapted to WB/Ozon managers?
