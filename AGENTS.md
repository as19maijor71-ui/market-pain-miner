# AGENTS.md — правила проекта для Codex

## Проект

Market Pain Miner для WB/Ozon — локальный исследовательский инструмент для
поиска продуктовых возможностей в Telegram-чатах про Wildberries и Ozon.

Главная идея: бот/CLI парсит чат, анализирует сообщения и выводит результат
на локальный сайт-выжимку, чтобы человеку было видно:

- что найдено в чате;
- из каких сообщений это взялось;
- какие боли и вопросы повторяются;
- какие готовые решения и конкуренты упоминаются;
- какие продуктовые гипотезы появились;
- что нужно проверить дальше.

## Карта Контекста

Читать только нужный контекст.

| Нужно | Читать |
|---|---|
| Бизнес-логика, аудитория, стратегия | `.business/INDEX.md` |
| Маркетплейсы | `.business/marketplaces/` |
| Целевые клиенты | `.business/audience/` |
| Продукты и offers | `.business/products/` |
| Цены и экономика | `.business/economics/` |
| Lead generation и positioning | `.business/marketing/` |
| Research rules и privacy | `.business/research/` |
| Локальные навыки проекта | `skills/` |
| Готовые промпты | `prompts/INDEX.md` |
| Планы | `plans/` |
| Память сессий | `retrospectives/` |
| Повторяемые процессы | `playbooks/INDEX.md` |

## Рабочий Процесс

1. Перед бизнес- или продуктовым решением читать `.business/INDEX.md` и
   конкретный файл под задачу.
2. Перед повторяемой работой проверять `skills/`, `prompts/INDEX.md` и
   `playbooks/INDEX.md`.
3. Перед нетривиальной фичей создать или обновить план в
   `plans/YYYY-MM-DD-name.md`.
4. Держать изменения scoped. Не рефакторить unrelated modules.
5. После значимой сессии добавить короткую ретроспективу в `retrospectives/`.
6. Для повторяемой работы добавлять или обновлять project-local skill, prompt
   или playbook.

## Project-Local Skills

В репозитории есть локальные skill packages:

- `skills/codex-project-ops`
- `skills/telegram-market-import`
- `skills/wb-ozon-pain-mining`
- `skills/product-opportunity-builder`

Использовать их через чтение соответствующего `SKILL.md`, когда задача
совпадает. Это versioned project assets, а не автоматически установленные
глобальные навыки.

## Data Rules

- Telegram exports — приватные market research data.
- Никогда не коммитить `data/exports/`, `data/db/`, `data/reports/`, `.env`
  или реальные данные участников чата.
- Не публиковать имена, Telegram handles, user IDs или приватные цитаты без
  отдельной проверки.
- Raw messages хранить локально.
- Публичные отчеты должны использовать aliases, анонимизированные snippets или
  агрегаты.
- Если файл может содержать secrets или personal data, смотреть только
  минимально нужные строки или metadata.

## Product Rules

Когда извлекаем opportunity из chat data, всегда фиксируем:

- какая проблема появилась;
- у кого эта проблема;
- как часто она появляется;
- как люди решают ее сейчас;
- есть ли реклама готового решения;
- первая версия MVP;
- почему seller/manager заплатит;
- сложность и риск;
- где это видно на локальном сайте-выжимке.

Default message categories:

- `pain`
- `question`
- `solution_ad`
- `tool_mention`
- `case`
- `insight`
- `offtopic`

Default marketplace themes:

- `analytics`
- `ads`
- `stock`
- `cards`
- `reviews`
- `prices`
- `margin`
- `supply`
- `penalties`
- `api`
- `managers`
- `automation`

## Coding Rules

- Для первого MVP предпочитать Python stdlib, если dependency не убирает
  реальную сложность.
- Importers должны быть deterministic и testable.
- AI/LLM classification держать за interface, чтобы можно было заменить local
  rules, OpenAI или manual review.
- SQLite — первый storage layer; FTS добавлять, когда search станет следующим
  bottleneck.
- CLI-команды должны работать до сложного UI.
- Локальный сайт-выжимка — обязательный видимый результат анализа, не “позже когда-нибудь”.

## Язык

Отвечать пользователю по-русски, если он не попросит иначе. Implementation
notes держать краткими и практичными.
