from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from app.classifiers.rules import (
    CLASSIFIER_NAME,
    CLASSIFIER_VERSION,
    classify_text,
    detect_topics,
)
from app.cli import (
    MAX_LATEST,
    run_classify,
    run_evaluate,
    run_import,
    run_stats,
    terminal_safe,
    validate_private_db_path,
)
from app.core.models import LabelRecord
from app.importers.telegram import load_telegram_export
from app.storage.sqlite import Database


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_result.json"
EXPECTED_LABELS = Path(__file__).parent / "fixtures" / "telegram_expected_labels.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_phase1_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


def test_synthetic_fixture_covers_phase1_export_shapes() -> None:
    result = load_telegram_export(FIXTURE)

    assert result.chat.name == "Synthetic Market Research Fixture"
    assert len(result.messages) == 8
    assert "Не могу" in result.messages[0].text
    assert result.messages[4].text == result.messages[0].text
    assert result.messages[5].forwarded_from == "Synthetic Public Source"
    assert result.messages[6].text == ""
    assert result.messages[7].text == ""
    assert result.messages[7].has_photo is True
    assert result.messages[7].media_type == "photo"


def test_import_is_idempotent_and_updates_existing_rows() -> None:
    result = load_telegram_export(FIXTURE)
    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            db.import_chat(result.chat, result.messages)
            db.import_chat(result.chat, result.messages)

            stats = db.stats()
            assert stats["messages"] == 8

            duplicate_rows = db.conn.execute(
                """
                SELECT chat_id, msg_id, COUNT(*) AS count
                FROM messages
                GROUP BY chat_id, msg_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            assert duplicate_rows == []

            updated_text = "Как посчитать маржу после новой комиссии и логистики?"
            updated_messages = [
                replace(message, text=updated_text) if message.msg_id == 2 else message
                for message in result.messages
            ]
            db.import_chat(result.chat, updated_messages)

            updated_row = db.conn.execute(
                """
                SELECT text
                FROM messages
                WHERE chat_id = ? AND msg_id = ?
                """,
                (result.chat.chat_id, 2),
            ).fetchone()
            assert updated_row["text"] == updated_text
            assert db.stats()["messages"] == 8
        finally:
            db.close()


def test_classify_persists_labels_and_stats_reports_distribution(
    capsys,
) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)

        db = Database(db_path)
        try:
            stats = db.stats()
            assert stats["messages"] == 8
            assert stats["labels"] == 8
            assert stats["unclassified"] == 0

            labels = {
                row["msg_id"]: row["category"]
                for row in db.conn.execute(
                    """
                    SELECT msg_id, category
                    FROM message_labels
                    ORDER BY msg_id
                    """
                )
            }
            assert labels == {
                1: "pain",
                2: "question",
                3: "solution_ad",
                4: "tool_mention",
                5: "pain",
                6: "question",
                7: "offtopic",
                8: "offtopic",
            }

            duplicate_labels = db.conn.execute(
                """
                SELECT
                    chat_id,
                    msg_id,
                    source,
                    classifier_name,
                    classifier_version,
                    COUNT(*) AS count
                FROM message_labels
                GROUP BY
                    chat_id,
                    msg_id,
                    source,
                    classifier_name,
                    classifier_version
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            assert duplicate_labels == []

            classifier_rows = db.conn.execute(
                """
                SELECT DISTINCT classifier_name, classifier_version, run_id
                FROM message_labels
                """
            ).fetchall()
            assert len(classifier_rows) == 1
            assert classifier_rows[0]["classifier_name"] == CLASSIFIER_NAME
            assert classifier_rows[0]["classifier_version"] == CLASSIFIER_VERSION
            assert classifier_rows[0]["run_id"]
        finally:
            db.close()

        capsys.readouterr()
        run_stats(db_path)
        output = capsys.readouterr().out

    assert "Messages: 8" in output
    assert "Labels: 8" in output
    assert "Unclassified messages: 0" in output
    assert "- pain: 2" in output
    assert "- question: 2" in output
    assert "- offtopic: 2" in output
    assert "- solution_ad: 1" in output
    assert "- tool_mention: 1" in output


def test_stats_latest_is_safe_by_default_and_raw_only_when_explicit(
    capsys,
) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        import_output = capsys.readouterr().out
        assert "Synthetic Market Research Fixture" not in import_output

        run_classify(db_path)
        capsys.readouterr()

        run_stats(db_path, latest=8)
        safe_output = capsys.readouterr().out
        assert "synthetic_participant" not in safe_output
        assert "Не могу" not in safe_output
        assert "https://example.test" not in safe_output
        assert "item 1:" in safe_output

        run_stats(db_path, latest=8, raw_local=True)
        raw_output = capsys.readouterr().out
        assert "synthetic_participant_04" in raw_output
        assert "https://example.test/tool" in raw_output


def test_effective_label_distribution_uses_one_label_per_message() -> None:
    result = load_telegram_export(FIXTURE)
    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            db.import_chat(result.chat, result.messages)
            labels = []
            for row in db.messages_for_classification():
                category, topics, confidence = classify_text(row["text"])
                labels.append(
                    LabelRecord(
                        chat_id=row["chat_id"],
                        msg_id=row["msg_id"],
                        category=category,
                        topics=topics,
                        confidence=confidence,
                        source="rules",
                        classifier_name=CLASSIFIER_NAME,
                        classifier_version=CLASSIFIER_VERSION,
                        run_id="test-rules-run",
                    )
                )
            db.upsert_message_labels(labels)
            db.upsert_message_labels(
                [
                    LabelRecord(
                        chat_id=result.chat.chat_id,
                        msg_id=1,
                        category="case",
                        topics=[],
                        confidence=0.99,
                        source="manual",
                        classifier_name="manual",
                        classifier_version="local",
                        run_id="manual-test-run",
                    )
                ]
            )

            stats = db.stats()
            assert stats["messages"] == 8
            assert stats["labels"] == 9

            distribution = {
                row["category"]: row["count"] for row in db.label_distribution()
            }
            assert sum(distribution.values()) == 8
            assert distribution["case"] == 1
            assert distribution["pain"] == 1

            latest_msg_1 = [
                row["category"] for row in db.latest_messages(20) if row["msg_id"] == 1
            ]
            assert latest_msg_1 == ["case"]
        finally:
            db.close()


def test_labels_cannot_be_inserted_without_a_message() -> None:
    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            with pytest.raises(sqlite3.IntegrityError):
                db.upsert_message_labels(
                    [
                        LabelRecord(
                            chat_id="missing_chat",
                            msg_id=404,
                            category="pain",
                            topics=[],
                            confidence=0.5,
                            source="rules",
                            classifier_name=CLASSIFIER_NAME,
                            classifier_version=CLASSIFIER_VERSION,
                            run_id="missing-run",
                        )
                    ]
                )
        finally:
            db.close()


def test_versioned_classifier_labels_are_stored_separately() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path, classifier_version="test-v1")
        run_classify(db_path, classifier_version="test-v2")

        db = Database(db_path)
        try:
            stats = db.stats()
            assert stats["messages"] == 8
            assert stats["labels"] == 16
            assert stats["unclassified"] == 0

            versions = {
                row["classifier_version"]: row["count"]
                for row in db.label_versions()
                if row["classifier_name"] == CLASSIFIER_NAME
            }
            assert versions["test-v1"] == 8
            assert versions["test-v2"] == 8

            duplicate_rows = db.conn.execute(
                """
                SELECT
                    chat_id,
                    msg_id,
                    source,
                    classifier_name,
                    classifier_version,
                    COUNT(*) AS count
                FROM message_labels
                GROUP BY
                    chat_id,
                    msg_id,
                    source,
                    classifier_name,
                    classifier_version
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            assert duplicate_rows == []
        finally:
            db.close()


def test_repeated_classifier_runs_keep_separate_run_ids() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_id_1 = run_classify(db_path, classifier_version="same-version")
        run_id_2 = run_classify(db_path, classifier_version="same-version")

        db = Database(db_path)
        try:
            stats = db.stats()
            assert stats["messages"] == 8
            assert stats["labels"] == 16

            run_counts = {
                row["run_id"]: row["count"]
                for row in db.conn.execute(
                    """
                    SELECT run_id, COUNT(*) AS count
                    FROM message_labels
                    WHERE classifier_version = 'same-version'
                    GROUP BY run_id
                    """
                )
            }
            assert run_counts == {run_id_1: 8, run_id_2: 8}
        finally:
            db.close()


def test_latest_classifier_run_uses_command_order_not_version_sort() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path, classifier_version="test-v2")
        run_classify(db_path, classifier_version="test-v1")

        db = Database(db_path)
        try:
            active_run = db.latest_classifier_run()
        finally:
            db.close()

    assert active_run is not None
    assert active_run["classifier_version"] == "test-v1"


def test_evaluate_reports_precision_and_errors(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_evaluate(db_path, EXPECTED_LABELS)
        output = capsys.readouterr().out

    assert "- pain: 1.00 (2/2)" in output
    assert "- question: 1.00 (2/2)" in output
    assert "- solution_ad: 1.00 (1/1)" in output
    assert "- tool_mention: 1.00 (1/1)" in output
    assert "Summary: 8/8 labels correct; macro precision 1.00; errors 0" in output
    assert "- none" in output
    assert result["correct"] == 8
    assert result["errors"] == []


def test_evaluate_rejects_missing_classifier_run() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path, classifier_version="existing-version")

        with pytest.raises(ValueError, match="No classifier labels found"):
            run_evaluate(db_path, EXPECTED_LABELS, classifier_version="missing-version")


def test_wb_ozon_domain_terms_detect_topics() -> None:
    topics = detect_topics(
        "дрр по рк вырос, спп режет цену, фбо fbo фбс fbs сц приемка, "
        "штрафы, выкупы, карточки, api, остатки, логистика и комиссия"
    )

    assert "ads" in topics
    assert "prices" in topics
    assert "supply" in topics
    assert "penalties" in topics
    assert "stock" in topics
    assert "cards" in topics
    assert "api" in topics
    assert "margin" in topics


def test_latest_limit_rejects_negative_and_excessive_values() -> None:
    with pytest.raises(ValueError):
        run_stats(Path("unused.sqlite"), latest=-1)

    with pytest.raises(ValueError):
        run_stats(Path("unused.sqlite"), latest=MAX_LATEST + 1)


def test_private_db_path_rejects_trackable_extensionless_paths() -> None:
    validate_private_db_path(Path("tests/_tmp_safe.sqlite"))
    validate_private_db_path(Path("data/db/local-cache"))
    validate_private_db_path(Path("external-cache.sqlite"), allow_external_db=True)

    with pytest.raises(ValueError, match="Refusing to store private Telegram data"):
        validate_private_db_path(Path("reports/research-cache"))

    with pytest.raises(ValueError, match="outside data/db"):
        validate_private_db_path(Path("external-cache.sqlite"))


def test_raw_local_output_sanitizes_terminal_control_chars(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        db = Database(db_path)
        try:
            db.conn.execute(
                """
                UPDATE messages
                SET author = ?, text = ?, date = ?
                WHERE msg_id = 1
                """,
                (
                    "author\x1b]52;c;clipboard\x07",
                    "text\x1b[31mred\x1b[0m",
                    "2026-05-19T09:00:00\x1b[2J",
                ),
            )
            db.conn.commit()
        finally:
            db.close()

        run_stats(db_path, latest=8, raw_local=True)
        output = capsys.readouterr().out

    assert "\x1b" not in output
    assert "\x07" not in output
    assert terminal_safe("text\x1b[31mred\x1b[0m") in output
