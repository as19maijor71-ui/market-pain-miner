from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
from uuid import uuid4

from app.cli import (
    run_classify,
    run_evaluate,
    run_import,
    run_review,
    run_summary,
)
from app.core.models import ChatRecord, LabelRecord, MessageRecord
from app.normalization import normalize_message_text
from app.storage.sqlite import Database


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_result.json"
EXPECTED_LABELS = Path(__file__).parent / "fixtures" / "telegram_expected_labels.json"
SOLUTIONS_FIXTURE = Path(__file__).parent / "fixtures" / "telegram_solutions_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_phase9_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


def make_message(msg_id: int, text: str) -> MessageRecord:
    return MessageRecord(
        chat_id="phase9_chat",
        msg_id=msg_id,
        date=f"2026-05-20T09:{msg_id:02d}:00",
        author=f"synthetic_author_{msg_id}",
        from_id=f"synthetic_from_{msg_id}",
        topic_id=None,
        reply_to=None,
        forwarded_from="",
        text=text,
        normalized_text=normalize_message_text(text),
        has_photo=False,
        has_file=False,
        media_type="",
        raw_json="{}",
    )


def test_known_fixture_pains_and_tool_mentions_leave_low_confidence_review(
    capsys,
) -> None:
    with temporary_db_path() as db_path:
        run_import(SOLUTIONS_FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_review(db_path)
        capsys.readouterr()

    low_confidence_ids = {
        item["message_id"]
        for item in result["low_confidence"]
        if item["reason"] == "low_confidence"
    }
    calibrated_ids = {"chat1:1", "chat1:2", "chat1:3", "chat1:5", "chat1:6"}

    assert low_confidence_ids.isdisjoint(calibrated_ids)
    assert all(
        item["category"] not in {"pain", "tool_mention"}
        for item in result["low_confidence"]
        if item["reason"] == "low_confidence"
    )


def test_weak_offtopic_and_ambiguous_messages_stay_review_candidates(
    capsys,
) -> None:
    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            db.import_chat(
                ChatRecord(
                    chat_id="phase9_chat",
                    name="Synthetic Phase 9",
                    type="public_supergroup",
                    total_messages=6,
                ),
                [
                    make_message(
                        1,
                        "Обсуждаем расписание вебинара без проблем маркетплейса.",
                    ),
                    make_message(2, "Обсуждаем отзывы без конкретной боли."),
                    make_message(3, "Как там остатки?"),
                    make_message(
                        4,
                        "Кто пробовал сайт https://example.test для вебинара?",
                    ),
                    make_message(5, "Я вручную поправил карточку, всё ок."),
                    make_message(6, "Вручную обновил цены, проблем нет."),
                ],
            )
        finally:
            db.close()

        run_classify(db_path)
        capsys.readouterr()
        result = run_review(db_path)
        capsys.readouterr()

    review_ids = {item["message_id"] for item in result["low_confidence"]}

    assert {"chat1:1", "chat1:2", "chat1:3", "chat1:4", "chat1:5", "chat1:6"}.issubset(
        review_ids
    )


def test_phase9_evaluate_precision_stays_green(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_evaluate(db_path, EXPECTED_LABELS)
        output = capsys.readouterr().out

    assert result["correct"] == 8
    assert result["macro_precision"] == 1.0
    assert result["errors"] == []
    assert "Summary: 8/8 labels correct; macro precision 1.00; errors 0" in output


def test_summary_is_privacy_safe_by_default(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(SOLUTIONS_FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_summary(db_path)
        output = capsys.readouterr().out

    payload = json.dumps(result, ensure_ascii=False)
    combined = output + payload

    assert "Research run summary" in output
    assert "Counts:" in output
    assert "Top clusters:" in output
    assert "Solutions:" in output
    assert "Opportunities:" in output
    assert "Review candidates:" in output
    assert "Quality gaps:" in output
    assert result["counts"]["messages"] == 9
    assert result["review_candidates"]["low_confidence_or_disputed_labels"] >= 1

    assert "Synthetic Solutions Fixture" not in combined
    assert "synthetic_participant" not in combined
    assert "3000000000" not in combined
    assert "https://sellerstock.test" not in combined
    assert "https://megaseller.test" not in combined
    assert "sellerstock.test" not in combined
    assert "megaseller.test" not in combined
    assert "@StockPilot" not in combined
    assert "Не могу свести" not in combined
    assert "Рекомендую бот" not in combined


def test_summary_uses_one_read_snapshot_when_run_changes_mid_read(
    capsys,
    monkeypatch,
) -> None:
    original_stats = Database.stats
    inserted = False

    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            db.conn.execute("PRAGMA journal_mode=WAL")
            db.import_chat(
                ChatRecord(
                    chat_id="phase9_chat",
                    name="Synthetic Phase 9",
                    type="public_supergroup",
                    total_messages=1,
                ),
                [make_message(1, "Не могу свести остатки WB и Ozon вручную.")],
            )
            db.upsert_message_labels(
                [
                    LabelRecord(
                        chat_id="phase9_chat",
                        msg_id=1,
                        category="offtopic",
                        topics=[],
                        confidence=0.25,
                        source="rules",
                        classifier_name="snapshot_rules",
                        classifier_version="v1",
                        run_id="snapshot-v1",
                    )
                ]
            )
        finally:
            db.close()

        def stats_then_new_run(self: Database) -> dict[str, int]:
            nonlocal inserted
            result = original_stats(self)
            if not inserted:
                inserted = True
                writer = Database(db_path)
                try:
                    writer.upsert_message_labels(
                        [
                            LabelRecord(
                                chat_id="phase9_chat",
                                msg_id=1,
                                category="pain",
                                topics=["stock"],
                                confidence=0.7,
                                source="rules",
                                classifier_name="snapshot_rules",
                                classifier_version="v2",
                                run_id="snapshot-v2",
                            )
                        ]
                    )
                finally:
                    writer.close()
            return result

        monkeypatch.setattr(Database, "stats", stats_then_new_run)
        result = run_summary(db_path)
        capsys.readouterr()

        final_db = Database(db_path)
        try:
            final_stats = original_stats(final_db)
        finally:
            final_db.close()

    assert inserted is True
    assert final_stats["labels"] == 2
    assert result["counts"]["labels"] == 1
    assert result["active_classifier"]["classifier_version"] == "v1"
    assert result["category_distribution"] == [{"category": "offtopic", "count": 1}]
