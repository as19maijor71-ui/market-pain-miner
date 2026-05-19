from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatRecord:
    chat_id: str
    name: str
    type: str
    total_messages: int


@dataclass(frozen=True)
class MessageRecord:
    chat_id: str
    msg_id: int
    date: str
    author: str
    from_id: str
    topic_id: str | None
    reply_to: int | None
    forwarded_from: str
    text: str
    has_photo: bool
    has_file: bool
    media_type: str
    raw_json: str


@dataclass(frozen=True)
class ImportResult:
    chat: ChatRecord
    messages: list[MessageRecord]

