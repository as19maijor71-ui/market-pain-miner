from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.models import ChatRecord, MessageRecord


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def close(self) -> None:
        self.conn.close()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                total_messages INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                chat_id TEXT NOT NULL,
                msg_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                author TEXT NOT NULL,
                from_id TEXT NOT NULL,
                topic_id TEXT,
                reply_to INTEGER,
                forwarded_from TEXT NOT NULL,
                text TEXT NOT NULL,
                has_photo INTEGER NOT NULL,
                has_file INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, msg_id),
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
            );

            CREATE TABLE IF NOT EXISTS message_labels (
                chat_id TEXT NOT NULL,
                msg_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                topics TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'rules',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, msg_id, source),
                FOREIGN KEY (chat_id, msg_id) REFERENCES messages(chat_id, msg_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date);
            CREATE INDEX IF NOT EXISTS idx_messages_author ON messages(author);
            CREATE INDEX IF NOT EXISTS idx_labels_category ON message_labels(category);
            """
        )
        self.conn.commit()

    def upsert_chat(self, chat: ChatRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO chats (chat_id, name, type, total_messages)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                total_messages = excluded.total_messages,
                updated_at = CURRENT_TIMESTAMP
            """,
            (chat.chat_id, chat.name, chat.type, chat.total_messages),
        )

    def upsert_messages(self, messages: list[MessageRecord]) -> int:
        before = self.conn.total_changes
        self.conn.executemany(
            """
            INSERT INTO messages (
                chat_id, msg_id, date, author, from_id, topic_id, reply_to,
                forwarded_from, text, has_photo, has_file, media_type, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, msg_id) DO UPDATE SET
                date = excluded.date,
                author = excluded.author,
                from_id = excluded.from_id,
                topic_id = excluded.topic_id,
                reply_to = excluded.reply_to,
                forwarded_from = excluded.forwarded_from,
                text = excluded.text,
                has_photo = excluded.has_photo,
                has_file = excluded.has_file,
                media_type = excluded.media_type,
                raw_json = excluded.raw_json
            """,
            [
                (
                    m.chat_id,
                    m.msg_id,
                    m.date,
                    m.author,
                    m.from_id,
                    m.topic_id,
                    m.reply_to,
                    m.forwarded_from,
                    m.text,
                    int(m.has_photo),
                    int(m.has_file),
                    m.media_type,
                    m.raw_json,
                )
                for m in messages
            ],
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def import_chat(self, chat: ChatRecord, messages: list[MessageRecord]) -> int:
        self.upsert_chat(chat)
        return self.upsert_messages(messages)

    def stats(self) -> dict[str, int]:
        chat_count = self.conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        message_count = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        label_count = self.conn.execute("SELECT COUNT(*) FROM message_labels").fetchone()[0]
        return {
            "chats": int(chat_count),
            "messages": int(message_count),
            "labels": int(label_count),
        }

    def latest_messages(self, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT chat_id, msg_id, date, author, substr(text, 1, 160) AS preview
                FROM messages
                ORDER BY date DESC
                LIMIT ?
                """,
                (limit,),
            )
        )

