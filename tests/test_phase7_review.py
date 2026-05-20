from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.cli import (
    load_expected_labels,
    run_classify,
    run_evaluate,
    run_import,
    run_opportunities,
    run_review,
)
from app.core.models import ChatRecord, MessageRecord
from app.normalization import normalize_message_text
from app.storage.sqlite import Database


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_result.json"
SOLUTIONS_FIXTURE = Path(__file__).parent / "fixtures" / "telegram_solutions_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_phase7_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


@contextmanager
def temporary_expected_path() -> Iterator[Path]:
    path = Path(__file__).parent / f"_tmp_phase7_expected_{uuid4().hex}.json"
    try:
        yield path
    finally:
        if path.exists():
            path.unlink()


def write_expected(path: Path, labels: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "name": "synthetic_phase7_control",
                "labels": labels,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def make_message(msg_id: int, text: str) -> MessageRecord:
    return MessageRecord(
        chat_id="phase7_chat",
        msg_id=msg_id,
        date=f"2026-05-19T12:{msg_id:02d}:00",
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


def make_chat_message(chat_id: str, msg_id: int, text: str) -> MessageRecord:
    return MessageRecord(
        chat_id=chat_id,
        msg_id=msg_id,
        date=f"2026-05-19T13:{msg_id:02d}:00",
        author=f"synthetic_author_{chat_id}_{msg_id}",
        from_id=f"synthetic_from_{chat_id}_{msg_id}",
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


def seed_opportunity_review_db(db_path: Path) -> None:
    db = Database(db_path)
    try:
        chat = ChatRecord(
            chat_id="phase7_chat",
            name="Synthetic Phase 7",
            type="public_supergroup",
            total_messages=4,
        )
        db.import_chat(
            chat,
            [
                make_message(
                    1,
                    "Сверка остатков не работает: WB одно, Ozon другое.",
                ),
                make_message(
                    2,
                    "Не могу свести остатки вручную после поставки.",
                ),
                make_message(
                    3,
                    "Как сверить остатки по складам, если таблица не сходится?",
                ),
                make_message(
                    4,
                    "Обсуждаем расписание вебинара без проблем маркетплейса.",
                ),
            ],
        )
    finally:
        db.close()


def stock_card(cards: object) -> object:
    for card in cards:
        if card.cluster_id == "pain:stock:stock_reconciliation":
            return card
    raise AssertionError("stock opportunity card not found")


def test_manual_label_correction_improves_evaluate_and_stays_separate(
    capsys,
) -> None:
    with temporary_expected_path() as expected_path, temporary_db_path() as db_path:
        write_expected(
            expected_path,
            [
                {"chat_id": "1000000000", "msg_id": 1, "category": "pain"},
                {"chat_id": "1000000000", "msg_id": 2, "category": "question"},
                {"chat_id": "1000000000", "msg_id": 3, "category": "solution_ad"},
                {"chat_id": "1000000000", "msg_id": 4, "category": "pain"},
                {"chat_id": "1000000000", "msg_id": 5, "category": "pain"},
                {"chat_id": "1000000000", "msg_id": 6, "category": "question"},
                {"chat_id": "1000000000", "msg_id": 7, "category": "offtopic"},
                {"chat_id": "1000000000", "msg_id": 8, "category": "offtopic"},
            ],
        )
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        before = run_evaluate(db_path, expected_path)
        before_output = capsys.readouterr().out

        run_review(
            db_path,
            set_label=("chat1:4", "pain"),
            expected_path=expected_path,
            topics="stock,automation",
        )
        review_output = capsys.readouterr().out

        after = run_evaluate(db_path, expected_path)
        after_output = capsys.readouterr().out

        db = Database(db_path)
        try:
            rows = db.conn.execute(
                """
                SELECT source, category, classifier_name, classifier_version
                FROM message_labels
                WHERE msg_id = 4
                ORDER BY source
                """
            ).fetchall()
        finally:
            db.close()

    assert before["correct"] == 7
    assert before["errors"] == [
        {"msg_id": 4, "expected": "pain", "actual": "tool_mention"}
    ]
    assert "Summary: 7/8 labels correct" in before_output

    assert after["correct"] == 8
    assert after["errors"] == []
    assert after["fixed_errors"] == [
        {
            "msg_id": 4,
            "expected": "pain",
            "previous": "tool_mention",
            "manual": "pain",
        }
    ]
    assert "- fixed msg_id=4 expected=pain was=tool_mention" in after_output
    assert "Manual correction stored:" in review_output
    assert "source=manual classifier=manual_review" in review_output

    by_source = {row["source"]: row for row in rows}
    assert by_source["rules"]["category"] == "tool_mention"
    assert by_source["manual"]["category"] == "pain"
    assert by_source["manual"]["classifier_name"] == "manual_review"


def test_manual_label_correction_changes_relevant_card_but_irrelevant_does_not(
    capsys,
) -> None:
    with temporary_db_path() as db_path:
        seed_opportunity_review_db(db_path)
        run_classify(db_path)
        capsys.readouterr()

        baseline = stock_card(run_opportunities(db_path))
        baseline_output = capsys.readouterr().out

        with pytest.raises(ValueError, match="no positive evaluate/card impact"):
            run_review(db_path, set_label=("chat1:4", "case"), topics="")
        irrelevant = stock_card(run_opportunities(db_path))
        capsys.readouterr()

        run_review(db_path, set_label=("chat1:3", "pain"), topics="stock")
        capsys.readouterr()
        improved = stock_card(run_opportunities(db_path))
        improved_output = capsys.readouterr().out

        db = Database(db_path)
        try:
            irrelevant_rows = db.conn.execute(
                """
                SELECT 1
                FROM message_labels
                WHERE msg_id = 4
                  AND source = 'manual'
                """
            ).fetchall()
        finally:
            db.close()

    assert baseline.support_status == "weak_signal"
    assert baseline.first_mvp == "unknown"
    assert "support_status=weak_signal" in baseline.frequency

    assert irrelevant.support_status == baseline.support_status
    assert irrelevant.first_mvp == baseline.first_mvp
    assert irrelevant.score.total == baseline.score.total

    assert improved.support_status == "supported"
    assert improved.first_mvp == "stock_reconciliation_checker"
    assert improved.score.total > baseline.score.total
    assert "support_status=supported" in improved.frequency
    assert "first_mvp=stock_reconciliation_checker" in improved_output

    assert irrelevant_rows == []


def test_manual_label_correction_that_introduces_evaluate_error_is_rejected(
    capsys,
) -> None:
    with temporary_expected_path() as expected_path, temporary_db_path() as db_path:
        write_expected(
            expected_path,
            [{"chat_id": "phase7_chat", "msg_id": 3, "category": "question"}],
        )
        seed_opportunity_review_db(db_path)
        run_classify(db_path)
        capsys.readouterr()

        with pytest.raises(ValueError, match="introduce an evaluate error"):
            run_review(
                db_path,
                set_label=("chat1:3", "pain"),
                expected_path=expected_path,
                topics="stock",
            )

        db = Database(db_path)
        try:
            rows = db.conn.execute(
                """
                SELECT 1
                FROM message_labels
                WHERE msg_id = 3
                  AND source = 'manual'
                """
            ).fetchall()
        finally:
            db.close()

    assert rows == []


def test_review_uses_one_stable_chat_alias_map(capsys) -> None:
    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            db.import_chat(
                ChatRecord(
                    chat_id="aaa_chat",
                    name="Synthetic A",
                    type="public_supergroup",
                    total_messages=1,
                ),
                [
                    make_chat_message(
                        "aaa_chat",
                        1,
                        "Обсуждаем расписание вебинара без маркетплейс боли.",
                    )
                ],
            )
            db.import_chat(
                ChatRecord(
                    chat_id="zzz_chat",
                    name="Synthetic Z",
                    type="public_supergroup",
                    total_messages=3,
                ),
                [
                    make_chat_message(
                        "zzz_chat",
                        1,
                        "Сверка остатков не работает: WB одно, Ozon другое.",
                    ),
                    make_chat_message(
                        "zzz_chat",
                        2,
                        "Не могу свести остатки вручную после поставки.",
                    ),
                    make_chat_message(
                        "zzz_chat",
                        3,
                        "Сверка остатков вручную занимает полдня.",
                    ),
                ],
            )
        finally:
            db.close()

        run_classify(db_path)
        capsys.readouterr()

        run_review(db_path)
        output = capsys.readouterr().out

    assert "message_id=chat1:1 category=offtopic" in output
    assert "message_id=chat2:1 category=pain" not in output
    assert "evidence_message_ids=chat2:1,chat2:2,chat2:3" in output
    assert "evidence_message_ids=chat1:1,chat1:2,chat1:3" not in output


def test_review_output_is_privacy_safe_by_default(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(SOLUTIONS_FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        run_review(db_path)
        output = capsys.readouterr().out

    assert "Review candidates" in output
    assert "Low-confidence/disputed labels:" in output
    assert "Weak-signal clusters:" in output
    assert "Opportunity cards needing review:" in output
    assert "chat1:" in output

    assert "Synthetic Solutions Fixture" not in output
    assert "synthetic_participant" not in output
    assert "https://sellerstock.test" not in output
    assert "https://megaseller.test" not in output
    assert "@StockPilot" not in output
    assert "Не могу свести" not in output
    assert "Рекомендую бот" not in output


def test_review_return_value_is_privacy_safe_by_default(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(SOLUTIONS_FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_review(db_path)
        capsys.readouterr()

    payload = json.dumps(result, ensure_ascii=False)
    assert "synthetic_participant" not in payload
    assert "1000000000" not in payload
    assert "https://sellerstock.test" not in payload
    assert "https://megaseller.test" not in payload
    assert "@StockPilot" not in payload
    assert "Не могу свести" not in payload
    assert "Рекомендую бот" not in payload

    assert all(isinstance(item, dict) for item in result["low_confidence"])
    assert all(isinstance(item, dict) for item in result["weak_clusters"])
    assert all(isinstance(item, dict) for item in result["noise_cases"])
    assert all(isinstance(item, dict) for item in result["review_cards"])
    assert all("preview" not in item for item in result["low_confidence"])


def test_expected_labels_path_rejects_private_or_secret_paths() -> None:
    forbidden_paths = (
        Path(".env"),
        Path("data/exports/result.json"),
        Path("data/db/labels.json"),
    )
    with temporary_db_path() as db_path:
        for expected_path in forbidden_paths:
            with pytest.raises(ValueError, match="Refusing to read expected labels"):
                run_review(db_path, expected_path=expected_path)
            with pytest.raises(ValueError, match="Refusing to read expected labels"):
                run_evaluate(db_path, expected_path)


def test_expected_labels_rejects_non_object_root() -> None:
    with temporary_expected_path() as expected_path:
        expected_path.write_text("[]", encoding="utf-8")

        with pytest.raises(ValueError, match="root must be an object"):
            load_expected_labels(expected_path)


def test_expected_labels_rejects_missing_required_fields() -> None:
    with temporary_expected_path() as expected_path:
        write_expected(expected_path, [{"chat_id": "phase7_chat", "msg_id": 1}])

        with pytest.raises(ValueError, match="missing required field"):
            load_expected_labels(expected_path)


def test_expected_labels_rejects_invalid_msg_id_and_category() -> None:
    with temporary_expected_path() as expected_path:
        write_expected(
            expected_path,
            [{"chat_id": "phase7_chat", "msg_id": "not-int", "category": "pain"}],
        )

        with pytest.raises(ValueError, match="invalid msg_id"):
            load_expected_labels(expected_path)

        write_expected(
            expected_path,
            [{"chat_id": "phase7_chat", "msg_id": 1, "category": "private_raw"}],
        )

        with pytest.raises(ValueError, match="invalid category"):
            load_expected_labels(expected_path)
