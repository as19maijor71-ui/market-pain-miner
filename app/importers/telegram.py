from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import ChatRecord, ImportResult, MessageRecord


def flatten_text(value: Any) -> str:
    """Flatten Telegram's mixed text/entity representation into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(value)


def normalize_chat_id(raw_id: Any) -> str:
    """Convert Telegram export chat IDs into t.me/c-compatible IDs when possible."""
    if raw_id is None:
        return ""

    raw_text = str(raw_id)
    try:
        value = int(raw_text)
    except ValueError:
        return raw_text

    if value < 0:
        abs_text = str(abs(value))
        if abs_text.startswith("100"):
            return str(abs(value) - 1_000_000_000_000)
        return str(abs(value))
    return str(value)


def load_telegram_export(path: str | Path) -> ImportResult:
    src = Path(path)
    with src.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    raw_messages = data.get("messages", [])
    chat_id = normalize_chat_id(data.get("id", ""))
    content_messages = [m for m in raw_messages if m.get("type") == "message" and "id" in m]

    chat = ChatRecord(
        chat_id=chat_id,
        name=str(data.get("name", "")),
        type=str(data.get("type", "")),
        total_messages=len(content_messages),
    )

    messages = [_normalize_message(chat_id, message) for message in content_messages]
    return ImportResult(chat=chat, messages=messages)


def _normalize_message(chat_id: str, message: dict[str, Any]) -> MessageRecord:
    topic_id = message.get("topic_id")
    return MessageRecord(
        chat_id=chat_id,
        msg_id=int(message["id"]),
        date=str(message.get("date", "")),
        author=str(message.get("from", "")),
        from_id=str(message.get("from_id", "")),
        topic_id=str(topic_id) if topic_id is not None else None,
        reply_to=message.get("reply_to_message_id"),
        forwarded_from=str(message.get("forwarded_from", "")),
        text=flatten_text(message.get("text", "")),
        has_photo=bool(message.get("photo")),
        has_file=bool(message.get("file")),
        media_type=str(message.get("media_type", "")),
        raw_json=json.dumps(message, ensure_ascii=False, separators=(",", ":")),
    )

