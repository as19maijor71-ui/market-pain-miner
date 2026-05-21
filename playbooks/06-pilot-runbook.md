# Playbook: Приватный Пилот

## Цель

Прогнать приватный Telegram export через MVP безопасно и получить наглядный
локальный сайт без копирования raw chat data в git-tracked файлы или публичные
заметки.

## Входы

- Telegram Desktop JSON export: `result.json`.
- Локальный путь к SQLite-базе.
- Optional expected-label JSON только для проверенного control sample.

## Безопасное Хранение

- Private exports: `data/exports/`, например `data/exports/pilot-001/result.json`.
- Local DB: `data/db/`, например `data/db/pilot-001.sqlite`.
- HTML reports: `data/reports/`, например `data/reports/pilot-001.html`.
- Не класть exports, DB, `.env`, screenshots с именами, raw terminal output и
  private drafts вне ignored-папок.

## Порядок Команд

Глобальные CLI options идут до subcommand.

```powershell
$Export = "data/exports/pilot-001/result.json"
$Db = "data/db/pilot-001.sqlite"
$Site = "data/reports/pilot-001-site"
$Profile = "data/reports/project-profile.json"

python -m app.cli --db $Db import $Export
python -m app.cli --db $Db classify
python -m app.cli profile-template --output $Profile
python -m app.cli --db $Db summary --limit 10
python -m app.cli --db $Db site --output-dir $Site --limit 20 --project-profile $Profile
python -m app.cli --db $Db review --limit 20
python -m app.cli --db $Db opportunities --limit 10
```

Локальный запуск сайта:

```powershell
python -m http.server 8765 -d $Site
```

Открыть `http://localhost:8765/`.

`summary` и `site` — первые результаты, которые можно обсуждать. Они не
должны печатать raw names, handles, URLs, private chat names, raw quotes и raw
chat IDs.

`profile-template` не читает приватные данные и пишет только безопасные
placeholder-поля для `site --project-profile`. Заполненный профиль хранить в
ignored-папке вроде `data/reports/`; если там появились частные заметки, не
переносить их в README, plans, retrospectives или PR-тексты.

## Optional Local Checks

```powershell
python -m app.cli --db $Db stats
python -m app.cli --db $Db clusters
python -m app.cli --db $Db solutions
```

`evaluate` использовать только для reviewed control sample, созданного именно
для этой базы.

## Raw Local Mode

`--raw-local` только для локальной отладки. Его output нельзя вставлять в
README, plans, retrospectives, issues, PRs, публичные отчеты, сообщения или
документы.

## Manual Review

Review candidates — это не финальные продуктовые решения, а подсказки, что
владельцу нужно проверить.

Manual labels:

```text
pain, question, solution_ad, tool_mention, case, insight, offtopic
```

Topics:

```text
analytics, ads, stock, cards, reviews, prices, margin, supply, penalties, api, managers, automation
```

Пример:

```powershell
python -m app.cli --db $Db review --set-label chat1:42 pain --topics stock,automation
python -m app.cli --db $Db site --output-dir $Site --limit 20
```

После генерации сайта открыть `for-you.html` и использовать блок “Команды
Review”: он показывает privacy-safe `review --set-label` команды по aliases и
follow-up команду для перегенерации сайта. Если нужны реальные локальные пути
в copyable commands, генерировать сайт с `--db-command-path`,
`--site-command-path` и `--profile-command-path`; эти значения не читать как
данные, а только печатать в generated commands.

## Cleanup

Проверить tracked changes и ignored private paths:

```powershell
git status --short
git status --short --ignored data/exports data/db data/reports
```

Проверка количеств без раскрытия путей:

```powershell
$PrivateFiles = @(
  Get-ChildItem -Force -Path data/exports,data/db,data/reports -Recurse -File -ErrorAction SilentlyContinue
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

## Оставшиеся Риски

- Quality: rules могут пропускать сленг, screenshots, reply context и
  неоднозначные объявления.
- Privacy: raw mode опасен, один скопированный блок может раскрыть данные.
- Performance: большие exports могут требовать batching.
- Product: владелец должен выбрать, какие выводы превращать в MVP.
