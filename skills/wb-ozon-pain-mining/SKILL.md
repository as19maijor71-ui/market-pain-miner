---
name: wb-ozon-pain-mining
description: Анализировать Telegram-сообщения из WB/Ozon-чатов, выделять боли, вопросы, решения, рекламу, кейсы, инсайты, темы и evidence-backed opportunity clusters.
---

# Поиск Болей WB/Ozon

## Процесс

1. Прочитать `.business/marketplaces/pain-taxonomy.md` и
   `.business/marketplaces/solution-taxonomy.md`.
2. Классифицировать сообщения:
   `pain`, `question`, `solution_ad`, `tool_mention`, `case`, `insight`,
   `offtopic`.
3. Добавить topic tags:
   `analytics`, `ads`, `stock`, `cards`, `reviews`, `prices`, `margin`,
   `supply`, `penalties`, `api`, `managers`, `automation`.
4. Группировать повторяющиеся проблемы по теме, формулировке, сегменту и
   workaround.
5. Для каждого вывода сохранять evidence message IDs.
6. Разделять WB-only, Ozon-only и общие marketplace-проблемы.
7. Показывать выводы на локальном сайте, чтобы человек видел цепочку от сообщений
   к гипотезам.

## Сильные Сигналы Боли

- повторяющаяся ручная работа;
- потеря денег или слив рекламного бюджета;
- штрафы, блокировки, missed deadlines;
- один и тот же вопрос от разных людей;
- менеджеры сообщают одну проблему по нескольким клиентам;
- запросы на tools, bots, tables, alerts, dashboards.

## Сигналы Готовых Решений

- ссылки на bots, services, dashboards, tables, courses, extensions;
- сообщения с “сделал”, “запустили”, “демо”, “пишите”, “подписка”;
- повторные рекомендации одного инструмента.

## Результат

Кластеры должны содержать:

- title;
- category;
- marketplace;
- audience segment;
- evidence message IDs;
- current workaround;
- possible product direction;
- confidence.

## References

Форма вывода описана в `references/classification-output.md`.
