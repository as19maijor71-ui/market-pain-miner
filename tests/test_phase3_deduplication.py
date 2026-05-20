from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from app.cli import run_classify, run_import, run_stats
from app.importers.telegram import load_telegram_export
from app.normalization import normalize_message_text
from app.storage.sqlite import Database


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_phase3_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


def test_normalized_text_is_deterministic() -> None:
    assert (
        normalize_message_text(
            "  Запустили СЕРВИС @PainBot\n"
            "https://Example.test/demo   Пишите в ЛС "
        )
        == "запустили сервис <handle> <url>"
    )
    assert normalize_message_text("WB   и\tOzon") == "wb и ozon"
    assert (
        normalize_message_text("Какая цена товара после СПП?")
        == "какая цена товара после спп?"
    )
    assert (
        normalize_message_text("Не понимаю, какая скидка съела маржу")
        == "не понимаю, какая скидка съела маржу"
    )
    assert (
        normalize_message_text(
            "Запустили наш сервис для отчетов по ДРР: демо на https://example.test/demo, подписка помесячно."
        )
        == "запустили наш сервис для отчетов по дрр"
    )


def test_import_stores_normalized_text() -> None:
    result = load_telegram_export(FIXTURE)
    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            db.import_chat(result.chat, result.messages)
            rows = {
                row["msg_id"]: row["normalized_text"]
                for row in db.conn.execute(
                    """
                    SELECT msg_id, normalized_text
                    FROM messages
                    ORDER BY msg_id
                    """
                )
            }
        finally:
            db.close()

    assert rows[1] == rows[5]
    assert "<url>" in rows[4]
    assert rows[7] == ""


def test_frequency_counts_exact_duplicates_and_keeps_categories_separate() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)

        db = Database(db_path)
        try:
            frequencies = {
                row["category"]: dict(row)
                for row in db.deduplicated_label_frequencies()
            }
            duplicate_groups = [dict(row) for row in db.duplicate_label_groups()]
            weak_messages = {
                row["msg_id"]: dict(row) for row in db.weak_evidence_messages()
            }
        finally:
            db.close()

    assert frequencies["pain"]["raw_count"] == 2
    assert frequencies["pain"]["unique_count"] == 1
    assert frequencies["pain"]["duplicate_count"] == 1
    assert frequencies["pain"]["repeated_count"] == 1
    assert frequencies["pain"]["weaker_evidence_count"] == 1

    assert frequencies["question"]["raw_count"] == 2
    assert frequencies["question"]["unique_count"] == 2
    assert frequencies["question"]["duplicate_count"] == 0
    assert frequencies["question"]["forwarded_count"] == 1
    assert frequencies["question"]["weaker_evidence_count"] == 1

    assert frequencies["solution_ad"]["raw_count"] == 1
    assert frequencies["solution_ad"]["unique_count"] == 1
    assert frequencies["tool_mention"]["raw_count"] == 1
    assert frequencies["tool_mention"]["unique_count"] == 1

    assert duplicate_groups == [
        {
            "category": "pain",
            "normalized_text": (
                "не могу свести остатки wb и ozon: в личном кабинете одно, "
                "в таблице другое, вручную уходит два часа."
            ),
            "raw_count": 2,
            "duplicate_count": 1,
            "forwarded_count": 0,
            "msg_ids": "1,5",
        }
    ]
    assert weak_messages[5]["is_repeated"] == 1
    assert weak_messages[5]["is_forwarded"] == 0
    assert weak_messages[6]["is_forwarded"] == 1
    assert weak_messages[6]["is_repeated"] == 0


def test_forwarded_null_is_not_weaker_evidence() -> None:
    json_path = Path(__file__).parent / f"_tmp_phase3_{uuid4().hex}.json"
    payload = {
        "id": -1001000000000,
        "name": "Synthetic Null Forward Fixture",
        "type": "public_supergroup",
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2026-05-19T10:00:00",
                "from": "synthetic_participant",
                "from_id": "synthetic_participant",
                "forwarded_from": None,
                "text": "Подскажите, где смотреть остатки?",
            }
        ],
    }
    try:
        json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = load_telegram_export(json_path)
    finally:
        if json_path.exists():
            json_path.unlink()

    assert result.messages[0].forwarded_from == ""

    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            db.import_chat(result.chat, result.messages)
        finally:
            db.close()
        run_classify(db_path)

        db = Database(db_path)
        try:
            weak_messages = list(db.weak_evidence_messages())
        finally:
            db.close()

    assert weak_messages == []


def test_existing_empty_normalized_text_is_backfilled_on_open() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)

        db = Database(db_path)
        try:
            db.conn.execute("UPDATE messages SET normalized_text = '' WHERE msg_id IN (1, 5)")
            db.conn.commit()
        finally:
            db.close()

        db = Database(db_path)
        try:
            empty_count = db.conn.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE msg_id IN (1, 5)
                  AND normalized_text = ''
                """
            ).fetchone()[0]
            frequencies = {
                row["category"]: dict(row)
                for row in db.deduplicated_label_frequencies()
            }
        finally:
            db.close()

    assert empty_count == 0
    assert frequencies["pain"]["raw_count"] == 2
    assert frequencies["pain"]["unique_count"] == 1
    assert frequencies["pain"]["duplicate_count"] == 1


def test_concurrent_open_can_migrate_old_message_schema() -> None:
    with temporary_db_path() as db_path:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE chats (
                    chat_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    total_messages INTEGER NOT NULL DEFAULT 0,
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE messages (
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
                    PRIMARY KEY (chat_id, msg_id)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        results = []
        lock = threading.Lock()

        def open_database() -> None:
            try:
                db = Database(db_path)
                db.close()
                result = "ok"
            except Exception as exc:  # pragma: no cover - assertion reports details
                result = f"{type(exc).__name__}: {exc}"
            with lock:
                results.append(result)

        threads = [threading.Thread(target=open_database) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        db = Database(db_path)
        try:
            columns = {
                row["name"]
                for row in db.conn.execute("PRAGMA table_info(messages)")
            }
        finally:
            db.close()

    assert results == ["ok", "ok"]
    assert "normalized_text" in columns


def test_stats_reports_deduplicated_counts_and_weaker_evidence(
    capsys,
) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        run_stats(db_path)
        output = capsys.readouterr().out

    assert "Deduplicated frequencies (active labels; scoring uses unique_count):" in output
    assert (
        "- pain: raw_count=2 unique_count=1 "
        "duplicate_count=1 weaker_evidence_count=1 scoring_count=1"
    ) in output
    assert (
        "- question: raw_count=2 unique_count=2 "
        "duplicate_count=0 weaker_evidence_count=1 scoring_count=2"
    ) in output
    assert "- solution_ad: raw_count=1 unique_count=1 duplicate_count=0" in output
    assert "- tool_mention: raw_count=1 unique_count=1 duplicate_count=0" in output
    assert "Exact duplicate groups:" in output
    assert "duplicate_group=1 raw_count=2 duplicate_count=1 messages=1,5" in output
    assert "Weaker evidence messages (forwarded/repeated):" in output
    assert "- pain msg_id=5 reason=repeated" in output
    assert "- question msg_id=6 reason=forwarded" in output
