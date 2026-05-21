# SQLite Schema

## Таблицы

- `chats` — metadata Telegram-чата.
- `messages` — raw и normalized messages.
- `classifier_runs` — версии и запуски классификатора.
- `message_labels` — labels от rules/manual review.

## Принцип

Raw data остается только в локальной SQLite-базе. Отчеты и публичные документы
используют aliases, агрегаты и evidence IDs.

## Будущее

FTS добавлять только когда поиск станет следующим узким bottleneck.
