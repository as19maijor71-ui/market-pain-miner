---
completed: false
last_completed_step: 4
started_at: 2026-05-19
project_type: commercial
stack: python-local-first
---

# CODEX_AUTOPILOT - onboarding for this project

This file is a lightweight Codex version of the Claude starter autopilot. It is not a command script. It is a step-by-step project setup protocol.

## Rule

If `completed: false`, continue from `last_completed_step`. After each completed step, update the frontmatter.

## Step 1. Project Calibration

Current working definition:

> Local market research system that imports Telegram chats about WB/Ozon, finds repeated seller and manager pains, extracts ready solutions and competitor ads, and turns them into product opportunities for small paid apps and bots.

Clarify and write into `.business/company/about.md`:

- project name
- one-line promise
- solo or team
- decision principles

## Step 2. Audience

Fill `.business/audience/`:

- primary buyer
- secondary buyer
- first narrow segment for MVP
- top objections
- buying journey

Recommended first segment:

> Marketplace managers and small WB/Ozon sellers who already feel operational pain and are willing to pay for automation that saves daily manual work.

## Step 3. Marketplace Taxonomy

Fill `.business/marketplaces/`:

- WB-specific pains
- Ozon-specific pains
- shared seller vocabulary
- pain taxonomy
- ready solution taxonomy

## Step 4. MVP Plan

Create a plan in `plans/` for the first working MVP:

1. Telegram JSON import.
2. SQLite storage.
3. Rule-based first classification.
4. Pain and solution reports.
5. Local dashboard or generated HTML report.

## Step 5. First Data Import

When a Telegram export is available:

```powershell
python -m app.cli import "C:\path\to\result.json"
python -m app.cli stats
```

Save lessons in `retrospectives/`.

## Step 6. Product Opportunity Loop

For every strong pain cluster, create an opportunity card with:

- problem
- segment
- evidence
- current workaround
- possible MVP
- monetization
- risks
- score

Use `playbooks/03-product-opportunity-card.md`.

## Step 7. Completion

When the first import, first report, and first opportunity card exist, set:

```yaml
completed: true
last_completed_step: 7
```
