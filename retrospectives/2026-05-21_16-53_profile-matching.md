# Ретроспектива: Profile Matching Для For-You

Дата/время: 2026-05-21 16:53

## Задача

Сделать так, чтобы `--project-profile` не только отображался в `for-you`, но
влиял на рекомендации локального сайта без LLM.

## Что Изменилось

- `app/cli.py`: добавлен deterministic matching по `focus_themes` и
  `avoid_themes` для topics, opportunities и insights.
- `app/web/site.py`: добавлены блоки “Совпадения С Фокусом”, “Следующая
  Проверка” и warnings профиля.
- `tests/test_static_site.py`: добавлены проверки profile matches, avoid
  priority, пустого профиля, privacy-safe output и валидного JSON.
- `README.md` и план project profile обновлены под новый flow.

## Результат

Done.

## Что Узнали

Даже без LLM профиль уже может менять порядок и priority рекомендаций, если
сопоставлять его с controlled labels и evidence aliases, а не с raw text.

## Следующий Шаг

После ручного review пилота проверить, достаточно ли `focus_themes` или нужен
отдельный вес для `decision_criteria`.
