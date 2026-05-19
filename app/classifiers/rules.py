from __future__ import annotations

import re

from app.classifiers.taxonomy import PAIN_TOPICS


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

SOLUTION_AD_MARKERS = [
    "запустил",
    "сделал бота",
    "наш сервис",
    "наш бот",
    "предлагаю",
    "пишите в лс",
    "промокод",
    "демо",
    "подписк",
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


def classify_text(text: str) -> tuple[str, list[str], float]:
    normalized = text.lower().strip()
    if not normalized:
        return "offtopic", [], 0.2

    topics = detect_topics(normalized)

    if _contains_any(normalized, SOLUTION_AD_MARKERS):
        return "solution_ad", topics, 0.65

    if _contains_url(normalized) and _contains_any(normalized, TOOL_MARKERS):
        return "tool_mention", topics, 0.55

    if _contains_any(normalized, PAIN_MARKERS):
        return "pain", topics, 0.55

    if "?" in normalized or normalized.startswith(("как ", "что ", "почему ", "где ", "кто ")):
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
    return any(marker in text for marker in markers)


def _contains_url(text: str) -> bool:
    return bool(re.search(r"https?://|t\.me/|@\w{4,}", text))

