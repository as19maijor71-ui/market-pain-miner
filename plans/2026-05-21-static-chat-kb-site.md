# План: multi-page Chat Knowledge Base site

Дата: 2026-05-21

## Цель

Привести продукт ближе к эталону `chat-kb-template.md`: после анализа
Telegram-чата генерировать не только один HTML-отчет, а локальный сайт с
несколькими страницами, JSON-данными и разделом “Для тебя”.

## Контекст

Переданные документы описывают рабочую логику:

- локальный сайт-выжимка из Telegram-чата;
- навигация по разделам;
- JSON-файлы как слой данных;
- страницы `index`, `people`, `tools`, `insights`, `niches`, `for-you`;
- `for-you` как самый ценный раздел;
- запуск через локальный сервер `http://localhost:8765/`;
- инкрементальные обновления от новых экспортов.

В этом проекте raw names, handles, URLs и private quotes по умолчанию не
выводятся даже в локальный отчет, если явно не включен raw режим.

## Фазы

- [x] Фаза 1: добавить команду генерации локального static site.
- [x] Фаза 2: создать JSON-слой данных для site: participants, tools,
  insights, niches, for-you, summary, chat_meta.
- [x] Фаза 3: создать HTML/CSS страницы с навигацией.
- [x] Фаза 4: покрыть site тестами приватности и структуры.
- [x] Фаза 5: обновить README/playbook под новый основной flow.

## Команда

```powershell
python -m app.cli --db data/db/pilot-001.sqlite site --output-dir data/reports/pilot-001-site --limit 20
```

Запуск:

```powershell
python -m http.server 8765 -d data/reports/pilot-001-site
```

## Проверка

- [x] `python -m pytest`
- [x] fixture flow `import -> classify -> site`
- [x] HTML/JSON не содержат raw fixture names, URLs, handles и private quotes.

## Результат

Done.

Проверено:

- `python -m pytest` — 74 passed.
- `python -m app.cli --db tests/_tmp_static_site_flow_<id>.sqlite import tests/fixtures/telegram_solutions_result.json`
- `python -m app.cli --db tests/_tmp_static_site_flow_<id>.sqlite classify`
- `python -m app.cli --db tests/_tmp_static_site_flow_<id>.sqlite site --output-dir tests/_tmp_static_site_flow_<id> --limit 10`
