# Playbook: Import Telegram Export

## Goal

Import Telegram Desktop `result.json` into the local SQLite database.

## Input

- Path to `result.json`.
- Optional database path.

## Command

```powershell
python -m app.cli import "C:\path\to\result.json"
python -m app.cli stats
```

## Checks

- Messages count is greater than zero.
- Chat name and chat id are detected.
- Text entities are flattened.
- Photo/file flags are preserved.
- No raw export is copied into git-tracked files.

## Output

- SQLite database in `data/db/chatkb.sqlite`.
- Import summary in terminal.
- Follow-up plan or retrospective if this is a real research session.

