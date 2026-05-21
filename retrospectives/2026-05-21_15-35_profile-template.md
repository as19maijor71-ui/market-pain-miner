# Ретроспектива: Profile Template CLI

Дата/время: 2026-05-21 15:35

## Задача

Добавить CLI-команду для создания privacy-safe JSON-шаблона project profile.

## Что Изменилось

- `app/cli.py`: добавлена команда `profile-template` и проверка безопасного
  output path.
- `tests/test_static_site.py`: добавлены проверки CLI, overwrite protection и
  path validation.
- `README.md` и `playbooks/06-pilot-runbook.md`: обновлен порядок локального
  запуска с `--project-profile`.

## Результат

Done.

## Что Узнали

Project profile лучше создавать в ignored-папке до генерации сайта, чтобы не
заносить личные product notes в tracked-файлы.

## Следующий Шаг

Проверить удобство заполнения шаблона на следующем локальном пилоте.
