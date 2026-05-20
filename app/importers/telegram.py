from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from app.core.models import ChatRecord, ImportResult, MessageRecord
from app.normalization import normalize_message_text


MAX_EXPORT_BYTES = 100 * 1024 * 1024
MAX_EXPORT_MESSAGES = 200_000


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


def text_or_empty(value: Any) -> str:
    if value is None:
        return ""
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
    _validate_export_file(src)
    try:
        with src.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except JSONDecodeError as exc:
        raise ValueError("Telegram export is not valid JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("Telegram export root must be a JSON object")

    raw_messages = data.get("messages", [])
    if not isinstance(raw_messages, list):
        raise ValueError("Telegram export 'messages' must be a list")
    if len(raw_messages) > MAX_EXPORT_MESSAGES:
        raise ValueError(
            "Telegram export has too many messages: "
            f"{len(raw_messages)} > {MAX_EXPORT_MESSAGES}"
        )

    chat_id = normalize_chat_id(data.get("id", ""))
    content_messages = _content_messages(raw_messages)

    chat = ChatRecord(
        chat_id=chat_id,
        name=str(data.get("name", "")),
        type=str(data.get("type", "")),
        total_messages=len(content_messages),
    )

    messages = [_normalize_message(chat_id, message) for message in content_messages]
    return ImportResult(chat=chat, messages=messages)


def _validate_export_file(path: Path) -> None:
    if not path.exists():
        raise ValueError("Telegram export does not exist")
    if not path.is_file():
        raise ValueError("Telegram export path is not a file")

    size = path.stat().st_size
    if size > MAX_EXPORT_BYTES:
        raise ValueError(
            "Telegram export is too large: "
            f"{size} bytes > {MAX_EXPORT_BYTES} bytes"
        )


def _content_messages(raw_messages: list[Any]) -> list[dict[str, Any]]:
    content_messages: list[dict[str, Any]] = []
    for index, message in enumerate(raw_messages):
        if not isinstance(message, dict):
            raise ValueError(f"Telegram export message at index {index} must be an object")
        if message.get("type") != "message":
            continue
        if "id" not in message:
            raise ValueError(f"Telegram content message at index {index} is missing 'id'")
        try:
            int(message["id"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Telegram content message at index {index} has invalid 'id'"
            ) from exc
        content_messages.append(message)
    return content_messages


def _normalize_message(chat_id: str, message: dict[str, Any]) -> MessageRecord:
    topic_id = message.get("topic_id")
    text = flatten_text(message.get("text", ""))
    return MessageRecord(
        chat_id=chat_id,
        msg_id=int(message["id"]),
        date=str(message.get("date", "")),
        author=str(message.get("from", "")),
        from_id=str(message.get("from_id", "")),
        topic_id=str(topic_id) if topic_id is not None else None,
        reply_to=message.get("reply_to_message_id"),
        forwarded_from=text_or_empty(message.get("forwarded_from")),
        text=text,
        normalized_text=normalize_message_text(text),
        has_photo=bool(message.get("photo")),
        has_file=bool(message.get("file")),
        media_type=str(message.get("media_type", "")),
        raw_json=json.dumps(message, ensure_ascii=False, separators=(",", ":")),
    )
