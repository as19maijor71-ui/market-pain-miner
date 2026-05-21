# Playbook: Импорт Telegram Export

## Цель

Безопасно импортировать Telegram Desktop `result.json` в локальную SQLite-базу.

## Шаги

1. Положить export в `data/exports/<run-id>/result.json`.
2. Создать отдельную базу в `data/db/<run-id>.sqlite`.
3. Запустить import.
4. Запустить classify.
5. Сначала смотреть `summary` или `report`, а не raw output.

```powershell
$Export = "data/exports/pilot-001/result.json"
$Db = "data/db/pilot-001.sqlite"

python -m app.cli --db $Db import $Export
python -m app.cli --db $Db classify
python -m app.cli --db $Db summary --limit 10
python -m app.cli --db $Db site --output-dir data/reports/pilot-001-site --limit 20
```

## Приватность

Не копировать raw messages, имена, handles, user IDs, private quotes и URL в
tracked-файлы.
