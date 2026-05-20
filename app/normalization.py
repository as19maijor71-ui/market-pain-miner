from __future__ import annotations

import re


URL_RE = re.compile(
    r"(?i)\b(?:https?://|www\.)\S+|\b(?:t\.me|telegram\.me)/\S+"
)
TELEGRAM_HANDLE_RE = re.compile(r"(?<![\w])@[a-zA-Z0-9_]{4,32}\b")
WHITESPACE_RE = re.compile(r"\s+")
AD_TAIL_PATTERNS = (
    re.compile(
        r"(?:(?:\s*[.!?:;|]\s*)|\s+)"
        r"(?:"
        r"пишите(?:\s+(?:в\s+лс|в\s+личку|мне))?|"
        r"подробности(?:\s+(?:в\s+лс|в\s+личку|по\s+ссылке))?|"
        r"подробнее(?:\s+(?:в\s+лс|в\s+личку|по\s+ссылке))?|"
        r"оставляйте\s+заявку"
        r")\b.*$"
    ),
    re.compile(
        r"\s*[.!?:;|]\s*"
        r"(?:демо|запись\s+на\s+демо)\b"
        r"(?:\s+(?:на|в|по)\s+<url>|\s+<url>)?.*$"
    ),
)


def normalize_message_text(text: str) -> str:
    """Return deterministic text used for exact duplicate counting."""
    normalized = text.lower()
    normalized = URL_RE.sub(" <url> ", normalized)
    normalized = TELEGRAM_HANDLE_RE.sub(" <handle> ", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    normalized = _strip_ad_tail(normalized)
    return WHITESPACE_RE.sub(" ", normalized).strip()


def _strip_ad_tail(text: str) -> str:
    previous = text
    while True:
        current = previous
        for pattern in AD_TAIL_PATTERNS:
            current = pattern.sub("", current).strip()
        if current == previous:
            return current
        previous = current
