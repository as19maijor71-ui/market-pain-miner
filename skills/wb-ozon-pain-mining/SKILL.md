---
name: wb-ozon-pain-mining
description: Analyze imported Telegram messages from WB/Ozon seller chats to classify pains, questions, ready solutions, competitor ads, cases, insights, marketplace topics, and evidence-backed opportunity clusters. Use when extracting market research from chats or ranking seller problems.
---

# WB/Ozon Pain Mining

## Workflow

1. Read `.business/marketplaces/pain-taxonomy.md` and `.business/marketplaces/solution-taxonomy.md`.
2. Classify messages into:
   `pain`, `question`, `solution_ad`, `tool_mention`, `case`, `insight`, `offtopic`.
3. Add topic tags:
   `analytics`, `ads`, `stock`, `cards`, `reviews`, `prices`, `margin`, `supply`, `penalties`, `api`, `managers`, `automation`.
4. Group repeated problems by topic, wording, segment, and current workaround.
5. Keep evidence message IDs for every useful conclusion.
6. Separate WB-only, Ozon-only, and shared marketplace problems.

## Strong Pain Signals

- repeated manual work
- money loss or ad budget waste
- penalties, blocked workflows, or missed deadlines
- confusion repeated by several users
- managers reporting the same issue across clients
- requests for tools, bots, tables, alerts, or dashboards

## Ready Solution Signals

- links to bots, services, dashboards, tables, courses, or extensions
- messages with "сделал", "запустили", "демо", "пишите", "подписка"
- repeated recommendations of the same tool

## Output

Produce clusters with:

- title
- category
- marketplace
- audience segment
- evidence message IDs
- current workaround
- possible product direction
- confidence

## References

Read `references/classification-output.md` for output shape.

