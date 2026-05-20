from __future__ import annotations

import re

from app.classifiers.taxonomy import PAIN_TOPICS


CLASSIFIER_NAME = "wb_ozon_rules"
CLASSIFIER_VERSION = "2026-05-20.1"

PAIN_MARKERS = [
    "проблем",
    "не могу",
    "не получается",
    "не работает",
    "ошиб",
    "слет",
    "штраф",
    "сливает",
    "просел",
    "потерял",
    "вручную",
    "долго",
    "дорого",
    "непонят",
]

DETERMINISTIC_PAIN_MARKERS = [
    "не могу",
    "не получается",
    "не работает",
    "ошиб",
    "слет",
    "штраф",
    "сливает",
    "просел",
    "потерял",
    "расхожд",
]

MANUAL_WORK_MARKERS = [
    "вручную",
]

MANUAL_WORK_PAIN_CONTEXT_MARKERS = [
    "долго",
    "час",
    "полдня",
    "каждый раз",
    "каждый день",
    "ежеднев",
    "постоянно",
    "не сход",
    "расхожд",
    "уходит",
]

SOLUTION_AD_MARKERS = [
    "запустил",
    "запустили",
    "сделал бота",
    "сделали",
    "наш сервис",
    "наш бот",
    "предлагаю",
    "пишите в лс",
    "промокод",
    "демо",
    "подписк",
    "тариф",
]

TOOL_MARKERS = [
    "бот",
    "сервис",
    "прилож",
    "сайт",
    "таблиц",
    "расширен",
    "дашборд",
    "парсер",
]

RECOMMENDATION_MARKERS = [
    "рекомендую",
    "советую",
    "пользуемся",
    "нам помог",
]

QUESTION_STARTS = (
    "как ",
    "что ",
    "почему ",
    "где ",
    "кто ",
    "подскажите",
    "посоветуйте",
)


def classify_text(text: str) -> tuple[str, list[str], float]:
    normalized = text.lower().strip()
    if not normalized:
        return "offtopic", [], 0.2

    topics = detect_topics(normalized)

    if _contains_any(normalized, SOLUTION_AD_MARKERS):
        return "solution_ad", topics, 0.65

    if _contains_url(normalized) and _contains_any(normalized, TOOL_MARKERS):
        confidence = 0.7 if topics else 0.55
        return "tool_mention", topics, confidence

    if _contains_any(normalized, RECOMMENDATION_MARKERS) and _contains_any(
        normalized,
        TOOL_MARKERS,
    ):
        return "tool_mention", topics, 0.55

    if _contains_any(normalized, PAIN_MARKERS):
        confidence = 0.7 if _is_deterministic_pain(normalized, topics) else 0.55
        return "pain", topics, confidence

    if "?" in normalized or normalized.startswith(QUESTION_STARTS):
        return "question", topics, 0.5

    if any(word in normalized for word in ["кейс", "получилось", "результат", "эксперимент"]):
        return "case", topics, 0.45

    if any(word in normalized for word in ["вывод", "лайфхак", "важно", "лучше", "не стоит"]):
        return "insight", topics, 0.45

    return "offtopic", topics, 0.25


def detect_topics(text: str) -> list[str]:
    found: list[str] = []
    for topic, markers in PAIN_TOPICS.items():
        if _contains_any(text, markers):
            found.append(topic)
    return found


def _contains_any(text: str, markers: list[str]) -> bool:
    return any(_contains_marker(text, marker) for marker in markers)


def _is_deterministic_pain(text: str, topics: list[str]) -> bool:
    if not topics:
        return False
    if _contains_any(text, DETERMINISTIC_PAIN_MARKERS):
        return True
    return _contains_any(text, MANUAL_WORK_MARKERS) and _contains_any(
        text,
        MANUAL_WORK_PAIN_CONTEXT_MARKERS,
    )


def _contains_marker(text: str, marker: str) -> bool:
    if marker.startswith("re:"):
        return bool(re.search(marker[3:], text))
    return marker in text


def _contains_url(text: str) -> bool:
    return bool(re.search(r"https?://|t\.me/|@\w{4,}", text))
