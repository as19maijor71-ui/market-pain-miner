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

## Фазы

- [x] Фаза 1: добавить чтение локального JSON project profile.
- [x] Фаза 2: подмешать profile в `for-you` и project metadata.
- [x] Фаза 3: покрыть персонализацию тестом и обновить README.
- [x] Фаза 4: добавить CLI-команду `profile-template` для безопасного
  шаблона `--project-profile`.

## Проверка

- [x] Команда или ручная проверка: `python -m pytest`
- [x] Команда или ручная проверка: `python -m pytest tests/test_static_site.py`

## Результат

Done: `profile-template` создает privacy-safe JSON-шаблон для локального
`--project-profile`.
