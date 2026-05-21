# Ретроспектива: review commands для for-you

Дата/время: 2026-05-21 17:11

## Задача

Сделать удобный privacy-safe review loop из локального сайта.

## Что Изменилось

- `site` получил command hints для DB/site/profile путей.
- `data/for-you.json` получил `review_commands` с aliases, suggested labels,
  controlled topics, `review --set-label` и follow-up `site`.
- `for-you.html` получил блок “Команды Review”.
- README и pilot runbook описывают использование command hints.

## Результат

Done.

## Что Узнали

Review-команды можно строить детерминированно из уже обезличенных
`profile_matches`, не обращаясь к raw Telegram data.

## Следующий Шаг

В пилоте проверить, какие suggested labels владелец реально использует чаще
всего, и при необходимости уточнить priority/limit команд.
