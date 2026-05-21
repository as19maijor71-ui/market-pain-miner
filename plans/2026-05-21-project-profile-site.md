# План: project profile для локального сайта

Дата: 2026-05-21

## Цель

Сделать раздел “Для тебя” персональнее: дать `site` локальный JSON-профиль
проекта с целевой аудиторией, фокус-темами и критериями решения.

## Контекст

Multi-page сайт уже генерируется из SQLite и safe summary. Raw Telegram data,
имена, handles, URL и приватные цитаты не должны попадать в tracked-файлы.
Project profile является локальным входом владельца и должен по умолчанию жить
в ignored-папке вроде `data/reports/`.

Следующий слой review loop должен давать владельцу команды для ручной проверки
прямо из `for-you.html`, но без раскрытия реальных DB paths, raw message text,
names, handles, URLs, user IDs или private chat names.

## Фазы

- [x] Фаза 1: добавить чтение локального JSON project profile.
- [x] Фаза 2: подмешать profile в `for-you` и project metadata.
- [x] Фаза 3: покрыть персонализацию тестом и обновить README.
- [x] Фаза 4: добавить CLI-команду `profile-template` для безопасного
  шаблона `--project-profile`.
- [x] Фаза 5: добавить deterministic profile matching для topics,
  opportunities и insights без LLM.
- [x] Фаза 6: добавить privacy-safe `review_commands` и command hints для
  локального review loop из `for-you.html`.

## Проверка

- [x] Команда или ручная проверка: `python -m pytest`
- [x] Команда или ручная проверка: `python -m pytest tests/test_static_site.py`
- [x] Команда или ручная проверка: `git diff --check`

## Результат

Done: `profile-template` создает privacy-safe JSON-шаблон для локального
`--project-profile`; `for-you` теперь показывает focus matches, warnings по
`avoid_themes`, рекомендуемую следующую ручную проверку и copyable
`review --set-label` команды с placeholder command paths по умолчанию.
