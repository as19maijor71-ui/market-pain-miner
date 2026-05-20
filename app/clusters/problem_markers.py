from __future__ import annotations

from app.core.models import ProblemMarkerDefinition


PROBLEM_MARKERS: tuple[ProblemMarkerDefinition, ...] = (
    ProblemMarkerDefinition(
        key="stock_reconciliation",
        topic="stock",
        label="stock reconciliation mismatch",
        synonyms=(
            "свести остатки",
            "сверить остатки",
            "сверка остатков",
            "сверки остатков",
            "остатки не сход",
            "остатки расход",
            "расхождение остатков",
            "остатки по складам",
        ),
    ),
    ProblemMarkerDefinition(
        key="margin_calculation",
        topic="margin",
        label="margin calculation after fees and logistics",
        synonyms=(
            "посчитать маржу",
            "считать маржу",
            "маржу после",
            "маржа уходит",
            "маржа в минус",
            "юнит экономика",
            "юнитка",
        ),
    ),
    ProblemMarkerDefinition(
        key="ad_budget_leak",
        topic="ads",
        label="ad budget leak or high DRR",
        synonyms=(
            "дрр вырос",
            "сливает бюджет",
            "реклама съедает",
            "ставки выросли",
            "рк не окуп",
            "кампания не окуп",
        ),
    ),
    ProblemMarkerDefinition(
        key="supply_acceptance_delay",
        topic="supply",
        label="supply acceptance delay or stuck shipment",
        synonyms=(
            "поставка зависла",
            "приемка зависла",
            "не приняли поставку",
            "слот поставки",
            "зависла на сц",
        ),
    ),
    ProblemMarkerDefinition(
        key="card_content_drop",
        topic="cards",
        label="card content, SEO, or conversion drop",
        synonyms=(
            "карточка просела",
            "просела карточка",
            "слетело описание",
            "слетел seo",
            "фото не проходят",
            "контент не проходит",
        ),
    ),
    ProblemMarkerDefinition(
        key="review_rating_issue",
        topic="reviews",
        label="reviews, questions, or rating issue",
        synonyms=(
            "отзывы пропали",
            "рейтинг просел",
            "не отвечают на вопросы",
            "вопросы покупателей",
            "негативные отзывы",
        ),
    ),
    ProblemMarkerDefinition(
        key="price_discount_confusion",
        topic="prices",
        label="price, discount, promo, or SPP confusion",
        synonyms=(
            "скидка съела",
            "спп режет",
            "цена поменялась",
            "акция съела",
            "промо не сход",
        ),
    ),
    ProblemMarkerDefinition(
        key="penalty_blocker",
        topic="penalties",
        label="penalty, claim, return, or blocking issue",
        synonyms=(
            "штраф прилетел",
            "штрафы пришли",
            "заблокировали кабинет",
            "претензия от",
            "возвраты без причины",
        ),
    ),
    ProblemMarkerDefinition(
        key="api_integration_break",
        topic="api",
        label="API key, token, or integration break",
        synonyms=(
            "api не работает",
            "апи не работает",
            "ключ слетел",
            "токен слетел",
            "интеграция отвалилась",
            "ошибка api",
        ),
    ),
    ProblemMarkerDefinition(
        key="client_reporting_manual",
        topic="managers",
        label="manual client or manager reporting",
        synonyms=(
            "отчет клиенту вручную",
            "отчеты клиентам вручную",
            "менеджер вручную",
            "каждый клиент просит отчет",
            "собирать отчеты клиентам",
        ),
    ),
    ProblemMarkerDefinition(
        key="manual_automation_gap",
        topic="automation",
        label="manual repeated work that needs automation",
        synonyms=(
            "делаю вручную",
            "собираю вручную",
            "нужен бот",
            "нужен скрипт",
            "автоматизировать вручную",
        ),
    ),
)
