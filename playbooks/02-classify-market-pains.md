# Playbook: Классификация Market Pains

## Цель

Разложить сообщения из Telegram-чата по категориям и темам, чтобы дальше
строить кластеры и гипотезы.

## Категории

- `pain` — явная боль или проблема.
- `question` — вопрос продавца/менеджера.
- `solution_ad` — кто-то продвигает bot, service, site, table, course или app.
- `tool_mention` — упоминание инструмента без явной рекламы.
- `case` — кейс или опыт.
- `insight` — полезное наблюдение.
- `offtopic` — не относится к исследованию.

## Темы

`analytics`, `ads`, `stock`, `cards`, `reviews`, `prices`, `margin`, `supply`,
`penalties`, `api`, `managers`, `automation`.

## Проверка

После `classify` запускать:

```powershell
python -m app.cli --db $Db summary --limit 10
python -m app.cli --db $Db site --output-dir data/reports/pilot-001-site --limit 20
python -m app.cli --db $Db review --limit 20
```
