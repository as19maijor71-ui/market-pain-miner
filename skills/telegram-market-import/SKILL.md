---
name: telegram-market-import
description: Импортировать Telegram Desktop exports для market research, безопасно хранить сообщения в SQLite и проверять качество импорта без публикации приватных данных.
---

# Импорт Telegram Market Data

## Процесс

1. Проверить, что export является Telegram Desktop `result.json`.
2. Хранить raw export только в `data/exports/`.
3. Импортировать в SQLite в `data/db/`.
4. Не копировать raw messages, names, handles, IDs или private quotes в docs.
5. После импорта запускать `classify`, `summary` и `report`.

## Безопасный Поток

```powershell
$Export = "data/exports/pilot-001/result.json"
$Db = "data/db/pilot-001.sqlite"

python -m app.cli --db $Db import $Export
python -m app.cli --db $Db classify
python -m app.cli --db $Db summary --limit 10
python -m app.cli --db $Db site --output-dir data/reports/pilot-001-site --limit 20
```

## Что Проверять

- количество импортированных чатов;
- количество сообщений;
- число labels после классификации;
- наличие локального сайта;
- отсутствие raw private data в tracked-файлах.

## References

Схема SQLite описана в `references/sqlite-schema.md`.
