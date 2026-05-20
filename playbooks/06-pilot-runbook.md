# Playbook: Private Pilot Run

## Goal

Run the first private Telegram export through the MVP safely, without copying raw chat data into git-tracked files or public notes.

## Inputs

- Telegram Desktop JSON export: `result.json`.
- Local SQLite database path.
- Optional expected-label JSON only if you are evaluating a reviewed control sample.

## Safe Storage

- Put private exports under `data/exports/`, for example `data/exports/pilot-001/result.json`.
- Put local databases under `data/db/`, for example `data/db/pilot-001.sqlite`.
- Do not put exports, databases, `.env`, screenshots with names, copied raw terminal output, or private report drafts outside ignored private folders.
- Before sharing any result, use aggregate counts, aliases like `chat1:123`, and anonymized snippets only after review.

## Command Order

Run global CLI options before the subcommand.

```powershell
$Export = "data/exports/pilot-001/result.json"
$Db = "data/db/pilot-001.sqlite"

python -m app.cli --db $Db import $Export
python -m app.cli --db $Db classify
python -m app.cli --db $Db summary --limit 10
python -m app.cli --db $Db review --limit 20
python -m app.cli --db $Db opportunities --limit 10
```

Use `summary` as the first report to copy or discuss. It is designed to avoid raw names, handles, URLs, private chat names, raw quotes, and raw chat IDs.

## Optional Local Checks

```powershell
python -m app.cli --db $Db stats
python -m app.cli --db $Db clusters
python -m app.cli --db $Db solutions
```

`evaluate` is only for a reviewed control sample created for this exact pilot DB. Do not use fixture expected labels on a private pilot DB; they will compare unrelated message IDs and produce misleading `missing` errors.

```powershell
python -m app.cli --db $Db evaluate --expected "path/to/pilot-reviewed-expected-labels.json"
```

Do not point `--expected` at `data/exports/`, `data/db/`, `.env`, or any file containing private raw Telegram data.

## Raw Local Mode

Use `--raw-local` only when you are debugging on your own machine and need to inspect exact evidence.

Commands with raw mode:

- `stats --latest N --raw-local` prints authors and message previews.
- `clusters --raw-local` prints raw chat IDs and normalized evidence text.
- `solutions --raw-local` prints raw solution URLs and Telegram handles.
- `review --raw-local` prints raw chat IDs and message previews.
- `opportunities --raw-local` prints raw chat IDs in evidence message IDs.

Never paste `--raw-local` output into README, plans, retrospectives, issues, PRs, public reports, chat messages, or docs. Prefer rerunning the command without `--raw-local` before copying anything.

## External DBs

By default, SQLite-like paths outside `data/db/` are rejected to avoid accidental tracked private data.

Allowed default paths:

- `data/db/*.sqlite`
- test temp DBs shaped like `tests/_tmp*.sqlite`

Only use `--allow-external-db` for an explicit local-only database outside the project, such as an encrypted/private folder. Replace the placeholder locally and do not paste the resolved path into tracked notes:

```powershell
$Db = "<local-private-db-path>"
python -m app.cli --db $Db --allow-external-db stats
```

Do not use `--allow-external-db` to write a DB into a git-tracked project folder.

## Manual Review

Review candidates are not final product decisions. They are prompts for the owner to inspect quality.

Message aliases such as `chat1:42` are local aliases generated from the current database contents. Use them only from the latest `review` output for the current DB, before importing another chat/export. After any new import, rerun `review` and copy fresh aliases.

Manual labels must use one of:

```text
pain, question, solution_ad, tool_mention, case, insight, offtopic
```

Manual corrections are intentionally narrow and should fix evidence quality or opportunity-card impact. When adding topics, use comma-separated controlled topics such as:

```text
analytics, ads, stock, cards, reviews, prices, margin, supply, penalties, api, managers, automation
```

Example:

```powershell
python -m app.cli --db $Db review --set-label chat1:42 pain --topics stock,automation
python -m app.cli --db $Db summary --limit 10
```

## Cleanup

After the pilot, check tracked changes and ignored private paths. Normal `git status --short` is not enough because private folders are intentionally ignored.

These checks print counts, not full local paths. Treat any non-zero count as local-only information and do not paste the detailed file listing into public notes or tracked docs.

```powershell
git status --short
git status --short --ignored data/exports data/db

$PrivateFiles = @(
  Get-ChildItem -Force -Path data/exports,data/db -Recurse -File -ErrorAction SilentlyContinue
)
$EnvFiles = @(
  Get-ChildItem -Force -Path .env,.env.* -ErrorAction SilentlyContinue
)
$UnexpectedDbFiles = @(
  Get-ChildItem -Recurse -File -Include *.sqlite,*.sqlite3,*.db -ErrorAction SilentlyContinue |
    Where-Object {
      $_.FullName -notlike "*\data\db\*" -and
      $_.FullName -notlike "*\data\exports\*"
    }
)

"private_files_in_ignored_dirs=$($PrivateFiles.Count)"
"env_files_present=$($EnvFiles.Count)"
"unexpected_sqlite_or_db_files=$($UnexpectedDbFiles.Count)"
```

Before committing or sharing project files:

- `git status --short` must not show copied raw Telegram output, private report drafts, `.env`, SQLite files, or other private artifacts.
- `git status --short --ignored data/exports data/db` may show ignored private folders only if you intentionally keep the pilot export/DB locally.
- `unexpected_sqlite_or_db_files` and `env_files_present` should be `0`.
- `private_files_in_ignored_dirs` may be greater than `0` only while you intentionally keep the pilot export/DB locally.

To delete a pilot DB and SQLite sidecar files when they are no longer needed:

```powershell
$Db = "data/db/pilot-001.sqlite"
foreach ($Suffix in @("", "-wal", "-shm", "-journal")) {
  $Path = "$Db$Suffix"
  if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path }
}
```

Delete the whole pilot export folder only after confirming you no longer need the original Telegram export. This removes `result.json` plus any Telegram media/file subfolders from the same pilot export.

First preview the folder locally. Do not paste this listing into tracked docs or public notes:

```powershell
$ExportRoot = (Resolve-Path -LiteralPath "data/exports").Path
$ExportDir = (Resolve-Path -LiteralPath "data/exports/pilot-001").Path
$Separator = [System.IO.Path]::DirectorySeparatorChar

if (-not $ExportDir.StartsWith($ExportRoot + $Separator, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to delete outside data/exports."
}

Get-ChildItem -LiteralPath $ExportDir -Force -Recurse |
  Select-Object Mode, Length, Name
```

Then delete only after the preview shows this folder contains only the disposable Telegram export:

```powershell
$ExportRoot = (Resolve-Path -LiteralPath "data/exports").Path
$ExportDir = (Resolve-Path -LiteralPath "data/exports/pilot-001").Path
$Separator = [System.IO.Path]::DirectorySeparatorChar

if (-not $ExportDir.StartsWith($ExportRoot + $Separator, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to delete outside data/exports."
}

$ConfirmDelete = Read-Host "Type DELETE to remove the pilot export folder"
if ($ConfirmDelete -ne "DELETE") {
  throw "Pilot export deletion cancelled."
}

Remove-Item -LiteralPath $ExportDir -Recurse -Force
```

## Remaining Pilot Risks

- Quality: fixture-proven rules may miss real WB/Ozon slang, mixed-language messages, screenshots, context from replies, and ambiguous ads.
- Privacy: raw mode is useful but dangerous; one copied terminal block can expose names, handles, URLs, user IDs, private chat names, or quotes.
- Performance: full private exports may produce more terminal output and longer clustering/opportunity runs than fixtures.
- Operator workflow: the owner must decide what to review, which manual corrections are justified, and what gets promoted into a sanitized opportunity note.
