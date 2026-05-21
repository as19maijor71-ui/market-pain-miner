# Market Pain Miner для WB/Ozon

Локальный инструмент для исследования Telegram-чатов про Wildberries и Ozon.
Он импортирует экспорт чата, находит повторяющиеся боли, вопросы, рекламу
решений, упоминания инструментов и собирает из этого продуктовые гипотезы.

Главный результат для человека: **локальный сайт-выжимка**, где видно:

- что было найдено в чате;
- какие сообщения стали доказательствами;
- какие кластеры боли повторяются;
- какие готовые решения и конкуренты упоминаются;
- какие гипотезы можно проверить дальше;
- какие места анализа требуют ручной проверки.

## Текущий Статус

Это локальный Python MVP:

- бизнес-контекст лежит в `.business/`;
- правила проекта лежат в `AGENTS.md`;
- протокол запуска и продолжения работы лежит в `CODEX_AUTOPILOT.md`;
- архитектура описана в `ARCHITECTURE.md`;
- локальные навыки проекта лежат в `skills/`;
- готовые промпты лежат в `prompts/`;
- повторяемые процессы лежат в `playbooks/`;
- планы работ лежат в `plans/`;
- CLI и генерация отчетов лежат в `app/`.

## Первый MVP

Первая версия работает от Telegram Desktop export:

1. Экспортируем историю чата в машинно-читаемый JSON.
2. Импортируем `result.json` в локальную SQLite-базу.
3. Классифицируем сообщения: боль, вопрос, реклама решения, упоминание
   инструмента, кейс, инсайт, оффтоп.
4. Строим кластеры, решения и карточки гипотез.
5. Генерируем локальный static site, который можно открыть в браузере.

## Команды

```powershell
$Export = "<local-result-json-path>"
python -m app.cli import $Export
python -m app.cli stats
```

Путь базы данных по умолчанию:

```text
data/db/chatkb.sqlite
```

## Приватный Пилот

Для первого реального приватного экспорта используйте runbook:

- [`playbooks/06-pilot-runbook.md`](./playbooks/06-pilot-runbook.md)

Безопасный порядок команд:

```powershell
$Export = "data/exports/pilot-001/result.json"
$Db = "data/db/pilot-001.sqlite"

python -m app.cli --db $Db import $Export
python -m app.cli --db $Db classify
python -m app.cli --db $Db summary --limit 10
python -m app.cli --db $Db site --output-dir data/reports/pilot-001-site --limit 20
python -m app.cli --db $Db review --limit 20
python -m app.cli --db $Db opportunities --limit 10
```

Для обсуждения сначала используйте `summary` или локальный сайт. Не копируйте в
tracked-файлы и публичные заметки сырой Telegram output, названия приватных
чатов, имена участников, Telegram handles, user IDs, URL или приватные цитаты.

`--raw-local` используйте только для локальной отладки на своей машине.
Команды с raw-режимом могут раскрывать авторов, превью сообщений, raw chat IDs,
normalized evidence text, URL, handles и raw evidence IDs.

## Локальный Сайт

Multi-page сайт генерируется из текущей SQLite-базы:

```powershell
python -m app.cli --db data/db/pilot-001.sqlite site --output-dir data/reports/pilot-001-site
```

Чтобы раздел `for-you.html` учитывал текущий продуктовый фокус, можно передать
локальный JSON-профиль проекта:

```powershell
python -m app.cli --db data/db/pilot-001.sqlite site `
  --output-dir data/reports/pilot-001-site `
  --project-profile data/reports/project-profile.json
```

Минимальная структура `project-profile.json`:

```json
{
  "project_name": "Market Pain Miner",
  "project_summary": "Локальный research bot для WB/Ozon-гипотез.",
  "target_segments": ["WB/Ozon seller", "marketplace manager"],
  "focus_themes": ["reviews", "penalties", "automation"],
  "offer_types": ["audit report", "telegram alert"],
  "decision_criteria": ["visible repeated pain", "clear willingness to pay"],
  "next_questions": ["Какие evidence IDs открыть первыми?"]
}
```

Профиль лучше хранить в ignored-папке вроде `data/reports/`, если в нем есть
частные продуктовые заметки.

Открыть через локальный сервер:

```powershell
python -m http.server 8765 -d data/reports/pilot-001-site
```

Потом открыть `http://localhost:8765/`.

Сайт содержит:

- `index.html` — дашборд;
- `for-you.html` — персональная страница “Для тебя”;
- `people.html` — карта участников через aliases;
- `tools.html` — тулзы, решения и competitor signals;
- `insights.html` — вопросы, кейсы и инсайты;
- `niches.html` — темы/ниши;
- `data/*.json` — слой данных для страниц.

`data/reports/` игнорируется git. Сайт по умолчанию privacy-safe: он показывает
aliases вроде `chat1:42`, агрегаты и controlled labels, но не печатает реальные
имена, handles, URL и сырые цитаты.

Быстрый single-page отчет тоже доступен:

```powershell
python -m app.cli --db data/db/pilot-001.sqlite report --output data/reports/pilot-001.html
```

## Навыки И Промпты

Локальные навыки Codex:

- `skills/codex-project-ops`
- `skills/telegram-market-import`
- `skills/wb-ozon-pain-mining`
- `skills/product-opportunity-builder`

Библиотека промптов:

- `prompts/INDEX.md`

Они хранятся в проекте, чтобы развиваться вместе с продуктом. Для
автоматического обнаружения Codex можно установить или скопировать папки
навыков в `$CODEX_HOME/skills` или `~/.codex/skills`.

## Приватность

Сырые Telegram-экспорты, локальные базы и реальный бизнес-контекст приватны и
игнорируются git. Перед передачей наружу артефакты должны быть
анонимизированы.

Перед завершением пилота используйте cleanup checklist из runbook. Не
полагайтесь только на `git status --short`: exports, DB, `.env` и SQLite-файлы
игнорируются git, поэтому могут лежать локально, хотя обычный статус молчит.

Минимальная проверка:

```powershell
git status --short
git status --short --ignored data/exports data/db data/reports
```

Полный cleanup checklist печатает количества, а не полные локальные пути.
Детальные списки локальных файлов не переносите в tracked-файлы и публичные
заметки.
