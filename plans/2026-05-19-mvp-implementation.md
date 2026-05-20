# План: MVP через доказательство платных возможностей

Дата: 2026-05-19

## Цель

Сделать не просто пайплайн импорта, а локальный инструмент, который помогает
выбрать первую платную идею для WB/Ozon продавцов или менеджеров на основе
доказательств из Telegram-чатов.

MVP считается полезным только если после импорта реальных локальных экспортов
он выдает короткий список возможностей, где видно:

- какая боль повторяется;
- кто предположительно страдает;
- на каких сообщениях держится вывод;
- что люди делают сейчас;
- есть ли готовые решения или реклама конкурентов;
- почему за это могут платить;
- где данных не хватает и надо писать `unknown`, а не додумывать.

## Главный критерий готовности MVP

Инструмент можно считать MVP, когда на 1-3 локальных Telegram-экспортах он
помогает выбрать одну первую платную гипотезу и честно показывает качество
сигнала.

Минимальная приемка:

- есть топ-5 возможностей, отсортированных по понятному скорингу;
- у каждой возможности есть блок доказательств (`evidence`): минимум 5
  уникальных сообщений или явный статус `not_enough_evidence`;
- частота считается по дедуплицированным сообщениям, а не по копипасте,
  пересылкам и рекламным повторам;
- карточка не заполняет важные поля фантазией: если нет доказательства, поле
  получает `unknown`;
- на ручной контрольной выборке видно качество классификации: точность
  (`precision`) по ключевым категориям `pain`, `question`, `solution_ad`,
  `tool_mention` не ниже 0.70 или есть список ошибок, который объясняет, почему
  порог пока не достигнут;
- проверка приватности отчета не находит явные Telegram handles, user IDs,
  названия приватных чатов и сырые неанонимные цитаты;
- оператор может ответить: "какую идею проверяем первой, почему, и какие данные
  еще надо собрать".

## Принципы

- Сначала ценность исследования, потом удобство интерфейса.
- Каждый отчетный вывод должен иметь доказательство или `unknown`.
- Приватность включена до первого отчета, а не после экспорта.
- Правила классификации должны иметь версию, чтобы старые и новые метки не
  смешивались незаметно.
- Частый вопрос не равен платной боли: готовность платить доказывается
  отдельными признаками.
- CLI остается основным интерфейсом до доказательства полезности.

## Текущее состояние

- `app.cli` умеет `import` и `stats`.
- `app.importers.telegram` читает Telegram Desktop `result.json`.
- `app.storage.sqlite` хранит `chats`, `messages`, `message_labels`.
- `app.classifiers.rules` классифицирует один текст, но результат еще не
  сохраняется в БД.
- `app.scoring.opportunity` содержит модель скоринга.
- Тесты покрывают только базовый импорт.

## Что убираем из MVP

- Dashboard переносится в список задач после MVP. Сейчас он не доказывает
  качество платных возможностей.
- CSV-экспорты переносим в список задач после MVP, пока не понятно, кто и зачем
  будет их использовать.
- Полную ручную систему relabel переносим после замера качества. Нужен не
  "контроль ради контроля", а способ находить и исправлять реальные ошибки.
- Расширенную полировку импортера по всем редким случаям не ставим первой задачей.
  Сначала нужен сквозной сигнал, потом добиваем частые реальные случаи.

## Этапы

- [x] Этап 0: приватность и безопасный вывод по умолчанию.
  - [x] Добавить правило: все команды отчетов и возможностей по умолчанию показывают
    агрегаты и анонимизированные фрагменты.
  - [x] Определить простую проверку приватности для отчетов: Telegram handles,
    user IDs, ссылки, названия приватных чатов, длинные сырые цитаты.
  - [x] Добавить в план вывода режим `--raw-local`, если нужен локальный просмотр
    исходного текста.
  - [x] Приемка: ни один отчетный файл не создается без безопасного режима или
    явного локального `--raw-local` флага.
  - Резюме проверки оркестратора: инвариант закрыт последующими фазами. CLI
    отчеты по умолчанию используют безопасные агрегаты/алиасы, raw output
    требует явного локального режима, privacy scans и phase12 audit не нашли
    tracked private exports, DB, `.env`, raw Telegram handles/user IDs/private
    chat names или private quotes.

- [x] Этап 1: тонкий сквозной срез вместо полировки транспорта.
  - [x] Создать синтетический `tests/fixtures/telegram_result.json` без реальных
    людей и чатов.
  - [x] В фикстуре покрыть: боль, вопрос, реклама решения, упоминание инструмента,
    копипаста/повтор, пересылка, пустой текст, сообщение только с медиа.
  - [x] Добавить тест идемпотентного импорта: проверять не только стабильный счетчик,
    но и отсутствие дублей по `(chat_id, msg_id)` и корректное обновление записи.
  - [x] Реализовать `python -m app.cli classify`, который сохраняет метки в SQLite.
  - [x] Приемка: одна команда import + classify + stats показывает сообщения,
    метки и распределение по категориям на фикстуре.
  - Резюме проверки оркестратора: фаза принята. Синтетическая фикстура покрывает
    требуемые формы сообщений, импорт идемпотентен по `(chat_id, msg_id)`,
    `classify` сохраняет 8 rule-based меток, `stats` показывает 8 сообщений,
    8 меток, 0 неклассифицированных и распределение по категориям. Проверки:
    `python -m compileall app tests`, `python -m pytest`, CLI-цепочка
    `import -> classify -> stats` на временной SQLite-БД.
  - Замечание по scope: в рабочем дереве есть отдельные изменения `skills/`,
    `prompts/`, `AGENTS.md`, `CODEX_AUTOPILOT.md` и README по проектным навыкам;
    они не блокируют фазу 1, но должны ревьюиться/коммититься отдельно от MVP
    thin slice.

- [x] Этап 2: качество классификации и доменная калибровка.
  - [x] Ввести `classifier_name`, `classifier_version`, `run_id` для меток.
  - [x] Добавить ручную контрольную выборку: файл ожидаемых меток для фикстуры и
    позднее локальный файл для реальных сообщений.
  - [x] Добавить команду или тест `evaluate`, который считает точность
    (`precision`) по ключевым
    категориям и пишет список типовых ошибок.
  - [x] Расширить словарь WB/Ozon терминов: ДРР, СПП, ФБО/FBO, ФБС/FBS, СЦ,
    приемка, штрафы, выкупы, карточки, РК, API, остатки, логистика, комиссия.
  - [x] Приемка: качество на контрольной выборке видно числом, а не ощущением;
    изменения правил можно сравнивать между версиями.
  - Результат: `message_labels` хранит метки по
    `(chat_id, msg_id, source, classifier_name, classifier_version)` и `run_id`.
    `classify` пишет текущую версию `wb_ozon_rules 2026-05-19.2`,
    `evaluate` сравнивает ее с `tests/fixtures/telegram_expected_labels.json`.
    На синтетической выборке precision: `pain` 1.00, `question` 1.00,
    `solution_ad` 1.00, `tool_mention` 1.00; ошибок нет.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`, CLI-цепочка
    `import -> classify -> evaluate -> stats` на временной SQLite-БД. `stats`
    показывает активную версию и `run_id`, а `evaluate` выводит precision и
    список ошибок. Нерушимые правила приватности не нарушены: реальных экспортов,
    `.env`, `data/db` и персональных Telegram-данных в изменениях не найдено.
    Остаточный риск: рабочее дерево все еще содержит отдельный пакет
    `skills/`/`prompts/` и связанные правки документации, их лучше держать
    отдельным ревью от MVP-фаз.

- [x] Этап 3: дедупликация и честная частота боли.
  - Определить `normalized_text`: нижний регистр, нормальные пробелы,
    ссылки/handles как placeholders, обрезка рекламных хвостов.
  - Считать точные дубли и похожие дубли отдельно.
  - Не смешивать боль, рекламу и упоминание инструмента в одну частоту.
  - Для пересланных и повторных сообщений хранить признак, что они слабее как
    доказательство.
  - Приемка: топ болей показывает `raw_count`, `unique_count`,
    `duplicate_count`, а скоринг использует `unique_count`.
  - Результат: `messages.normalized_text` заполняется детерминированно при
    импорте и мигрируется для старых локальных БД. `stats` показывает
    дедуплицированные частоты по активным меткам отдельно для `pain`,
    `question`, `solution_ad`, `tool_mention`: `raw_count`, `unique_count`,
    `duplicate_count`, `weaker_evidence_count`. На фикстуре боль с копипастой
    дает `raw_count=2`, `unique_count=1`, `duplicate_count=1`; повтор
    `msg_id=5` виден как `repeated`, пересылка `msg_id=6` как `forwarded`.
    Частотный вывод явно показывает `scoring_count=unique_count`. Похожие
    near-duplicates сознательно не объединяются до явной логики этапа 4.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`, CLI-цепочка
    `import -> classify -> stats` на временной SQLite-БД. Критерий сошелся:
    `stats` показывает `raw_count`, `unique_count`, `duplicate_count`,
    `weaker_evidence_count`, exact duplicate group `messages=1,5` и слабые
    доказательства `msg_id=5`/`repeated`, `msg_id=6`/`forwarded`. Нарушений
    приватности не найдено; `@PainBot` встречается только как синтетический
    тестовый handle для проверки нормализации. Остаточный риск: похожие
    near-duplicates пока не считаются отдельной метрикой, их нужно вводить
    только через явные маркеры/кластеры следующего этапа.

- [x] Этап 4: явное определение кластеров.
  - [x] Кластер боли = категория `pain` или `question` + тема + нормализованный
    маркер проблемы.
  - [x] Минимальная поддержка для кандидата: 3 уникальных сообщения или статус
    `weak_signal`.
  - [x] Добавить таблицу/модель результата кластеризации только если запросы к БД
    станут неудобными; сначала достаточно методов запросов к БД.
  - [x] Синонимы и близкие формулировки держать в явном словаре, без магического
    "похоже".
  - [x] Приемка: каждый кластер объясняет, какие сообщения вошли, почему они
    объединены, и какие похожие сообщения были отброшены как шум.
  - Результат: добавлены явные problem markers, кластерные модели и
    `python -m app.cli clusters`. На синтетической кластерной фикстуре есть
    `pain:stock:stock_reconciliation` со статусом `supported`:
    `raw_count=5`, `unique_count=3`, `duplicate_count=2`,
    `weaker_evidence_count=2`; и `question:margin:margin_calculation` со
    статусом `weak_signal`. Evidence выводится через безопасные `chatN:msg_id`
    алиасы, а `solution_ad`, `tool_mention`, `offtopic` с похожим marker
    отображаются как `rejected/noise`, не как кластеры боли.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`, CLI-цепочка
    `import -> classify -> clusters` на `tests/fixtures/telegram_clusters_result.json`.
    Критерий сошелся: каждый кластер показывает ids evidence, причину
    объединения, support status и rejected/noise ids. Нерушимые правила не
    нарушены: реальные экспорты/БД/секреты не читались и не появились в diff.
    Остаточный риск: rejected/noise пока покрывает в основном не-кластерные
    категории с тем же marker; более тонкие пограничные pain/question случаи
    лучше добавить позже на реальных ошибках контрольной выборки.

- [x] Этап 5: упоминания решений без искажения конкурентной карты.
  - [x] Разделять `solution_ad`, `tool_mention`, `recommendation`, `affiliate_or_spam`
    хотя бы на уровне правил/флагов.
  - [x] Для каждого решения вытаскивать: тип, URL/handle, обещание, кому продают,
    признаки рекламы, цену если видна, ID сообщений-источников.
  - [x] Не считать рекламу доказательством готовности платить без дополнительных
    признаков: обсуждения цены, рекомендаций, повторных упоминаний, жалоб на
    альтернативы.
  - [x] Приемка: отчет по решениям показывает не просто ссылки, а степень доверия к
    тому, что это реальная конкурентная/покупательская активность.
  - Результат: добавлен отдельный extractor `app.solutions` и команда
    `python -m app.cli solutions`. Отчет группирует solution mentions в
    solution records, показывает subtype/flags (`solution_ad`, `tool_mention`,
    `recommendation`, `affiliate_or_spam`), solution type, безопасные locator
    aliases, promise, target audience, ad signals, price, source ids и
    `trust/payment_signals`. Default output скрывает raw URL/handles; локальный
    просмотр доступен только через `--raw-local`.
  - На синтетической фикстуре `telegram_solutions_result.json` реклама
    `SellerStock` получает `payment_status=ad_only_unproven`, потому что сама
    реклама без дополнительных trust/payment signals не считается доказательством
    willingness to pay. `StockPilot` получает сильный сигнал из рекомендации,
    обсуждения цены, платной подписки и повторного независимого упоминания.
    `MegaSeller` помечается как affiliate/spam-like с жалобой на альтернативу.
  - Проверено, что solution mentions не попадают в pain frequency/cluster
    evidence: в кластере боли остаются только pain/question evidence, а
    solution/tool сообщения отображаются как rejected/noise.
  - Остаточный риск: extractor намеренно детерминированный и узкий; не пытается
    разобрать все рекламные форматы, сложные много-ссылочные посты и скрытые
    партнерские сообщения без явных маркеров.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`, CLI-цепочка
    `import -> classify -> solutions` на
    `tests/fixtures/telegram_solutions_result.json`. Критерий сошелся:
    `solutions` выводит 3 записи, скрывает raw URL/handles в default output,
    показывает `trust_level`, `payment_status`, subtype/flags, locator aliases,
    promise, audience, price, source ids и trust/payment signals. `SellerStock`
    остается `ad_only_unproven`, `StockPilot` получает
    `trust_signals_present`, а affiliate/spam-like `MegaSeller` отделен от
    pain evidence. Нерушимые правила не нарушены: найденные URL/handles
    находятся только в синтетических фикстурах/тестах или выводятся сырыми
    только через `--raw-local`.

- [x] Этап 6: карточки возможностей с доказательствами.
  - [x] Карточка должна хранить доказательство (`evidence`) для каждого сильного утверждения.
  - [x] Обязательные поля: problem, audience, frequency, current workaround,
    ready solutions, first MVP, payment reason, complexity, risk, score.
  - [x] Если доказательств нет, писать `unknown`.
  - [x] Готовность платить выводить из признаков: платные аналоги, реклама решений,
    жалобы на потери денег/времени, менеджерский/агентский сценарий,
    повторяемость процесса.
  - [x] Приемка: `opportunities` генерирует топ-5 карточек, где каждое поле либо
    подтверждено доказательством, либо помечено `unknown`.
  - Результат: добавлен `app.opportunities` с моделью `OpportunityCard`,
    field-level `OpportunityEvidence` и командой
    `python -m app.cli opportunities`. Карточки строятся из supported/weak
    clusters, дедуплицированной `unique_count` частоты, weak evidence flags и
    solution records. Default output показывает только безопасные aliases
    `chatN:msg_id`, controlled labels/reasons и не печатает raw URL/handles,
    участников или сырые цитаты.
  - На синтетической fixture `telegram_solutions_result.json` получилась
    карточка `pain:stock:stock_reconciliation`: problem `stock reconciliation
    mismatch`, audience `marketplace_managers,marketplace_sellers`,
    frequency `unique_count=3`, workaround
    `manual_spreadsheet_or_cabinet_reconciliation`, ready solutions
    `telegram_bot/trust_signals_present` и `analytics_service/ad_only_unproven`,
    first MVP `stock_reconciliation_checker`, payment reason из trust/payment
    signals, потерь времени, repeated workflow и manager scenario.
  - `unknown` проверен тестами на слабом кластере без аудитории, workaround,
    ready solution, MVP и payment evidence. Реклама alone остается
    `ad_only_unproven` и не создает `payment_reason`.
  - Остаточный риск: scoring пока rule-based и узкий; complexity/risk/MVP
    выводятся из controlled marker rules, а не из отдельной экспертной модели.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`, CLI-цепочка
    `import -> classify -> opportunities` на
    `tests/fixtures/telegram_solutions_result.json`. Критерий сошелся:
    `opportunities` выводит карточку с обязательными полями, field-level
    evidence, `unknown` для неподтвержденных полей, score breakdown и safe
    source aliases. Нерушимые правила не нарушены: default output не печатает
    raw URL/handles, участников, user IDs или сырые цитаты; найденные privacy
    scan совпадения находятся в синтетических тестах/фикстурах и правилах.

- [x] Этап 7: минимальный цикл проверки только для улучшения качества.
  - [x] Показывать низкоуверенные метки и спорные кластеры.
  - [x] Разрешить ручную правку только там, где это влияет на метрику качества или
    карточку возможности.
  - [x] Фиксировать источник как `manual` и не смешивать с `rules`.
  - [x] Приемка: после ручной проверки можно повторно посчитать качество и увидеть,
    какие ошибки реально исправлены.
  - Результат: добавлена команда `python -m app.cli review` с alias
    `review-candidates`. Она показывает low-confidence/disputed labels,
    weak-signal clusters, disputed/noise cases и opportunity cards needing
    review. Ручная правка доступна через `--set-label`, сохраняется отдельной
    меткой `source=manual` с classifier metadata и не перетирает rule labels.
  - `evaluate` теперь считает effective labels как базовый classifier run плюс
    последние manual overrides и выводит manual impact: fixed/introduced errors.
    `opportunities` использует effective labels, поэтому ручная правка может
    менять support status, поля карточки и score только через evidence-backed
    cluster/solution flow.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`,
    `python -m pytest tests/test_phase7_review.py -q`, CLI-цепочка
    `import -> classify -> review -> evaluate -> opportunities` на
    `tests/fixtures/telegram_result.json`. Критерий сошелся: review показывает
    кандидатов, manual labels отделены от rules, evaluate показывает impact, а
    тесты покрывают улучшение метрики, изменение карточки, отказ от
    нерелевантной/ухудшающей правки и safe default output. Нерушимые правила не
    нарушены: real exports, `data/db`, `.env` и реальные Telegram-данные не
    трогались; raw previews доступны только через явный `--raw-local`.
  - Остаточный риск: для произвольных реальных чатов metric-impact можно строго
    доказать только при наличии локального expected-labels файла; без него
    `--set-label` должен проходить только если меняет opportunity card.

- [x] Этап 8: первый локальный research run и hardening MVP.
  - [x] Создать план `plans/2026-05-20-phase8-local-research-run.md`.
  - [x] Выполнить end-to-end pipeline
    `import -> classify -> stats -> clusters -> solutions -> opportunities -> review`.
  - [x] Запустить `evaluate` при наличии matching expected-labels sample.
  - [x] Сформировать sanitized run summary: counts, top cards, review candidates,
    quality gaps и privacy notes.
  - [x] Исправлять только блокирующие pipeline/privacy/test reliability баги.
  - [x] Добавить retrospective после сессии.
  - Результат: приватный export path не был передан, поэтому фаза выполнена на
    синтетических fixtures. Smoke-run на `telegram_solutions_result.json` прошел
    всю CLI-цепочку и дал: 1 chat, 9 messages, 9 labels, 0 unclassified,
    1 supported cluster, 3 solution records, 1 opportunity card, 6 review
    candidates, 3 disputed/noise cases. Matching synthetic expected-labels sample
    на `telegram_result.json` дал 8/8 correct, macro precision 1.00, errors 0.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`, repeated CLI smoke-run
    `import -> classify -> stats -> clusters -> solutions -> opportunities -> review`
    и `import -> classify -> evaluate`. Критерий сошелся: есть safe runbook для
    приватного экспорта, fixture pipeline проходит, expected-label validation
    проходит, sanitized summary не содержит raw private data, временные SQLite
    файлы удалены. Нерушимые правила не нарушены: `data/exports`, `data/db`,
    `.env`, реальные Telegram-данные, raw handles/user IDs и приватные названия
    чатов не появились в git status.
  - Остаточный риск: реальный private-export run еще не выполнен, потому что путь
    к экспорту не был предоставлен. Основной найденный hardening gap - слишком
    консервативная confidence calibration, из-за которой корректные marketplace
    messages попадают в review queue.

- [x] Этап 9: confidence calibration и privacy-safe summary.
  - [x] Создать план `plans/2026-05-20-phase9-confidence-summary.md`.
  - [x] Откалибровать confidence только для уже доказанных deterministic rule cases.
  - [x] Добавить тесты: корректные fixture pains/tool mentions уходят из review
    только по причине низкой confidence; weak/offtopic/ambiguous остаются review
    candidates; `evaluate` не ухудшается.
  - [x] Добавить `python -m app.cli summary` с counts, top clusters, solutions,
    opportunities, review candidates и quality gaps.
  - [x] Проверить, что summary default output не печатает raw URLs/handles,
    authors, user IDs, private chat names или raw quotes.
  - [x] Добавить retrospective после сессии.
  - Результат: classifier version обновлен до `2026-05-20.1`; deterministic
    `pain` и `tool_mention` cases получают confidence `0.70`, а вопросы,
    weak/offtopic/ambiguous cases остаются reviewable. На
    `telegram_solutions_result.json` low-confidence/disputed labels снизились
    с 6 до 1, disputed/noise cases остались видимыми, supported opportunity card
    не скрыта. `summary` собирает один privacy-safe research report без ручной
    склейки вывода нескольких команд.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`,
    `python -m pytest tests/test_phase9_confidence_summary.py -q`, CLI smoke-run
    `import -> classify -> stats -> clusters -> solutions -> opportunities -> review -> summary`
    и `import -> classify -> evaluate -> review -> summary`. Критерий сошелся:
    review стал менее шумным на известных корректных cases, weak/offtopic/ambiguous
    cases остались в очереди, precision держится на 8/8 и macro precision 1.00,
    summary выводит counts, distribution, frequencies, clusters, solutions,
    opportunities, review candidates и quality gaps. Нерушимые правила не
    нарушены: реальные экспорты/БД/секреты не читались и не появились в git
    status; найденные privacy-scan совпадения относятся к синтетическим
    фикстурам/тестам или правилам запрета.
  - Остаточный риск: calibration подтверждена только синтетическими fixtures.
    Следующий реальный сигнал нужно получать на owner-provided private export,
    не расширяя taxonomy и не поднимая confidence без новых negative tests.

- [x] Этап 10: real-export pilot readiness и release hygiene.
  - [x] Создать план `plans/2026-05-20-phase10-pilot-readiness.md`.
  - [x] Обновить README или отдельный runbook для безопасного pilot flow:
    `import -> classify -> summary -> review -> opportunities`.
  - [x] Добавить checklist: export/db storage, raw output handling,
    `--raw-local`, cleanup, ignored private paths и remaining pilot risks.
  - [x] Проверить CLI help/errors для `--db`, `--raw-local`,
    `--allow-external-db`, expected labels и manual categories.
  - [x] Запустить fixture smoke pipeline through `summary`, `review` и
    `opportunities`, а также `python -m pytest`.
  - [x] Добавить retrospective после сессии.
  - Результат: добавлен `playbooks/06-pilot-runbook.md`, README ссылается на
    runbook, `playbooks/INDEX.md` обновлен. Runbook описывает safe storage в
    ignored `data/exports/` и `data/db/`, safe command order, локальный-only
    `--raw-local`, expected-label ограничения, manual review categories,
    cleanup с count-only checks и preview + явным `DELETE` перед удалением
    export folder.
  - Резюме проверки оркестратора: фаза принята. Проверки:
    `python -m compileall app tests`, `python -m pytest`, CLI help для основных
    команд, error checks для external DB path, `--allow-external-db`, private
    expected labels, non-JSON expected labels и invalid manual category,
    fixture smoke `import -> classify -> summary -> review -> opportunities`.
    Критерий сошелся: owner может безопасно запустить первый pilot без raw data
    в tracked docs, `summary` остается первым копируемым artifact, cleanup
    checklist не печатает полные private paths в docs. Нерушимые правила не
    нарушены: реальные экспорты/секреты не читались, временные phase10 SQLite
    файлы удалены, `git status --short` не показывает `data/exports`,
    `data/db`, `.env` или raw Telegram data. `git status --short --ignored`
    показывает локальный ignored `data/db/`; его содержимое не инспектировалось.
  - Остаточный риск: реальный owner-run pilot еще не выполнен. Следующая фаза
    должна работать только с явно предоставленным локальным export path и
    фиксировать только sanitized findings.

- [x] Этап 11: owner-provided private pilot run.
  - [x] Создать план `plans/2026-05-20-phase11-private-pilot-run.md`.
  - [x] Если export path предоставлен, выполнить private pilot; если нет -
    не имитировать real pilot и записать blocked state.
  - [x] Подготовить sanitized findings template без чтения приватных данных.
  - [x] Запустить fixture smoke
    `import -> classify -> summary -> review -> opportunities`.
  - [x] Запустить `python -m pytest` и проверить privacy status.
  - [x] Добавить retrospective после сессии.
  - Результат: explicit owner-provided local export path не был передан, поэтому
    real private pilot не запускался. План фазы фиксирует blocked state,
    подтверждает, что no real export was read/imported/classified/summarized,
    и содержит sanitized findings template для counts, top opportunities,
    review noise, missed/weak patterns, privacy notes, performance notes и next
    quality gaps.
  - Резюме проверки оркестратора: фаза принята как safe fallback. Проверки:
    `python -m compileall app tests`, `python -m pytest`, fixture smoke с GUID
    temp DB через `import -> classify -> summary -> review -> opportunities`,
    privacy scan по tracked files и status checks для `data`, `.env` и temp DBs.
    Критерий сошелся: без explicit export path приватный pilot не выполнялся,
    tracked docs не содержат raw Telegram data, names, handles, user IDs,
    private chat names или raw quotes; temporary phase11 SQLite удален.
    `git status --short --ignored` показывает локальный ignored `data/db/`,
    его содержимое не инспектировалось.
  - Остаточный риск: главный блокер остается тем же - нужен explicit local
    Telegram export path от владельца. До его появления следующие работы должны
    быть только release/commit hygiene и privacy audit, без чтения real data.

- [x] Этап 12: release/commit hygiene и privacy audit.
  - [x] Создать план `plans/2026-05-20-phase12-release-hygiene.md`.
  - [x] Сформировать release checklist, разделив MVP pipeline,
    docs/runbooks/plans/retrospectives и separately reviewable changes.
  - [x] Провести privacy audit tracked/candidate files и ignored private paths
    без чтения содержимого `data/exports` или `data/db`.
  - [x] Запустить `python -m pytest`.
  - [x] Запустить fixture smoke
    `import -> classify -> summary -> review -> opportunities`.
  - [x] Записать sanitized release notes и retrospective.
  - Результат: release checklist и privacy audit зафиксированы, real private
    pilot остается явно blocked без owner-provided export path. Дополнительно
    закрыты security-review замечания: ошибки Telegram importer не раскрывают
    приватные export paths, expected-label JSON validation стала строже, а
    competitor-scan playbook удерживает raw links/handles/authors local-only.
  - Резюме проверки оркестратора: фаза принята. Проверки: `python -m compileall
    app tests`, `python -m pytest` (70 passed), fixture smoke с GUID temp DB
    через `import -> classify -> summary -> review -> opportunities`, privacy
    scan по tracked files/status для `data`, `.env`, temp DBs и raw Telegram
    indicators. Критерий сошелся: private data не читались, tracked private
    paths отсутствуют, real pilot не имитировался, временная phase12 SQLite
    удалена. Локальный ignored `data/db/` присутствует как private storage; его
    содержимое не инспектировалось.
  - Остаточный риск: real pilot все еще требует explicit local Telegram export
    path от владельца. `architecture/` в workspace отсутствует, поэтому
    privacy-invariants проверялись по `AGENTS.md`; это зафиксировано в плане
    фазы.

## Первый батч реализации

- [x] Создать синтетическую Telegram-фикстуру и ожидаемые метки.
- [x] Добавить тесты импорта: идемпотентность, отсутствие дублей, корректное
  обновление записи.
- [x] Добавить хранение меток с `classifier_name`, `classifier_version`,
  `run_id`.
- [x] Реализовать `python -m app.cli classify`.
- [x] Расширить `stats`: метки по категориям, версия классификатора,
  последние `run_id` и количество неклассифицированных сообщений.
- [x] Добавить первый тест качества на фикстуре: точность (`precision`) по ключевым
  категориям и список ошибок.

Этот батч полезен, потому что сразу проверяет не только "код работает", а
"классификация дает измеримый сигнал".

## После MVP

- Локальный dashboard.
- CSV-экспорт для внешней обработки.
- SQLite FTS и расширенный поиск.
- LLM-классификация через тот же интерфейс.
- Live Telegram automation.
- Продвинутая near-duplicate кластеризация.

## Проверка

- [x] `python -m compileall app tests`
- [x] `python -m pytest`
- [x] `python -m app.cli --db tests/_tmp_phase1_cli.sqlite import tests/fixtures/telegram_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase1_cli.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase1_cli.sqlite stats`
- [x] `python -m app.cli --db tests/_tmp_phase2_cli.sqlite evaluate`
- [x] `python -m app.cli --db tests/_tmp_phase3_cli.sqlite import tests/fixtures/telegram_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase3_cli.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase3_cli.sqlite stats`
- [x] `python -m app.cli --db tests/_tmp_phase4_cli.sqlite import tests/fixtures/telegram_clusters_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase4_cli.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase4_cli.sqlite clusters`
- [x] `python -m pytest tests/test_phase5_solutions.py -q`
- [x] `python -m app.cli --db tests/_tmp_phase5_cli.sqlite import tests/fixtures/telegram_solutions_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase5_cli.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase5_cli.sqlite solutions`
- [x] `python -m pytest tests/test_phase6_opportunities.py -q`
- [x] `python -m app.cli --db tests/_tmp_phase6_cli.sqlite import tests/fixtures/telegram_solutions_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase6_cli.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase6_cli.sqlite opportunities`
- [x] `python -m pytest tests/test_phase7_review.py -q`
- [x] `python -m app.cli --db tests/_tmp_phase7_cli.sqlite import tests/fixtures/telegram_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase7_cli.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase7_cli.sqlite review`
- [x] `python -m app.cli --db tests/_tmp_phase7_cli.sqlite evaluate`
- [x] `python -m app.cli --db tests/_tmp_phase7_cli.sqlite opportunities`
- [x] `python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite import tests/fixtures/telegram_solutions_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite stats`
- [x] `python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite clusters`
- [x] `python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite solutions`
- [x] `python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite opportunities --limit 5`
- [x] `python -m app.cli --db tests/_tmp_phase8_pipeline.sqlite review`
- [x] `python -m app.cli --db tests/_tmp_phase8_eval.sqlite import tests/fixtures/telegram_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase8_eval.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase8_eval.sqlite evaluate --expected tests/fixtures/telegram_expected_labels.json`
- [x] `python -m pytest tests/test_phase9_confidence_summary.py -q`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite import tests/fixtures/telegram_solutions_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite stats`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite clusters`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite solutions`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite opportunities --limit 5`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite review`
- [x] `python -m app.cli --db tests/_tmp_phase9_pipeline.sqlite summary`
- [x] `python -m app.cli --db tests/_tmp_phase9_eval.sqlite import tests/fixtures/telegram_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase9_eval.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase9_eval.sqlite evaluate --expected tests/fixtures/telegram_expected_labels.json`
- [x] `python -m app.cli --db tests/_tmp_phase9_eval.sqlite review`
- [x] `python -m app.cli --db tests/_tmp_phase9_eval.sqlite summary`
- [x] `python -m app.cli --help`
- [x] `python -m app.cli summary --help`
- [x] `python -m app.cli review --help`
- [x] `python -m app.cli opportunities --help`
- [x] `python -m app.cli stats --help`
- [x] `python -m app.cli evaluate --help`
- [x] Error check: reject external SQLite-like DB without `--allow-external-db`
- [x] Error check: allow explicit local-only external DB with `--allow-external-db`
- [x] Error check: reject expected labels under `data/db`
- [x] Error check: reject non-JSON expected labels
- [x] Error check: reject invalid manual category
- [x] `python -m app.cli --db tests/_tmp_phase10_smoke.sqlite import tests/fixtures/telegram_solutions_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase10_smoke.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase10_smoke.sqlite summary --limit 3`
- [x] `python -m app.cli --db tests/_tmp_phase10_smoke.sqlite review --limit 3`
- [x] `python -m app.cli --db tests/_tmp_phase10_smoke.sqlite opportunities --limit 3`
- [x] `python -m app.cli --db tests/_tmp_phase11_smoke_<guid>.sqlite import tests/fixtures/telegram_solutions_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase11_smoke_<guid>.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase11_smoke_<guid>.sqlite summary --limit 3`
- [x] `python -m app.cli --db tests/_tmp_phase11_smoke_<guid>.sqlite review --limit 3`
- [x] `python -m app.cli --db tests/_tmp_phase11_smoke_<guid>.sqlite opportunities --limit 3`
- [x] `python -m app.cli --db tests/_tmp_phase12_smoke_<guid>.sqlite import tests/fixtures/telegram_solutions_result.json`
- [x] `python -m app.cli --db tests/_tmp_phase12_smoke_<guid>.sqlite classify`
- [x] `python -m app.cli --db tests/_tmp_phase12_smoke_<guid>.sqlite summary --limit 5`
- [x] `python -m app.cli --db tests/_tmp_phase12_smoke_<guid>.sqlite review --limit 5`
- [x] `python -m app.cli --db tests/_tmp_phase12_smoke_<guid>.sqlite opportunities --limit 5`
- [x] Security regression checks for sanitized importer errors and expected
  labels validation.
- [x] Проверка приватности отчета: нет handles, user IDs, приватных названий чатов и
  длинных сырых цитат.

## Итог

План обновлен: теперь он проверяет не сам факт пайплайна, а способность пайплайна
выдавать достоверные, приватные и коммерчески осмысленные возможности.

Следующий шаг: owner decision - commit/PR, private pilot с явно переданным
local export path или остановка на MVP snapshot. Новые фазы не запускаются без
отдельного решения владельца.
