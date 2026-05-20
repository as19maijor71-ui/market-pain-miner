---
name: telegram-market-import
description: Safely import Telegram Desktop result.json exports for local WB/Ozon market research. Use when the user provides a Telegram export path, asks to ingest or update chats, inspect import stats, or debug Telegram JSON normalization and SQLite storage.
---

# Telegram Market Import

## Workflow

1. Confirm the input is Telegram Desktop `result.json` in machine-readable JSON format.
2. Keep the export in `data/exports/` or another private local path. Do not commit it.
3. Import with:

```powershell
$Export = "<local-result-json-path>"
python -m app.cli import $Export
```

4. Verify with:

```powershell
python -m app.cli stats --latest 10
```

5. If import fails, inspect the JSON shape before changing parser logic.

## Expected Parser Behavior

- Read only messages with `type == "message"`.
- Flatten Telegram text arrays into plain text.
- Preserve `chat_id`, `msg_id`, date, author, `from_id`, `topic_id`, reply id, forwarded source, media flags, and raw JSON.
- Upsert by `(chat_id, msg_id)` so newer exports do not duplicate messages.

## Privacy

Raw exports, database files, and participant data stay local. Public reports should use anonymized evidence or aggregate counts.

## References

Read `references/sqlite-schema.md` when changing storage or debugging imports.
