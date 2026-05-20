from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.classifiers.rules import classify_text
from app.cli import run_classify, run_clusters, run_import, run_solutions
from app.clusters import build_cluster_report
from app.core.models import (
    ChatRecord,
    LabelRecord,
    MessageRecord,
    SolutionSourceMessage,
)
from app.importers.telegram import load_telegram_export
from app.normalization import normalize_message_text
from app.solutions import build_solution_report
from app.storage.sqlite import Database


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_solutions_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_phase5_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


def solution_message(
    msg_id: int,
    text: str,
    *,
    category: str = "solution_ad",
    author: str | None = None,
    from_id: str | None = None,
) -> SolutionSourceMessage:
    return SolutionSourceMessage(
        chat_id="synthetic_chat",
        msg_id=msg_id,
        date=f"2026-05-19T12:{msg_id:02d}:00",
        author=author or f"synthetic_author_{msg_id}",
        from_id=from_id or f"synthetic_from_{msg_id}",
        category=category,
        topics=(),
        text=text,
        normalized_text=normalize_message_text(text),
        forwarded_from="",
    )


def test_solution_fixture_has_required_synthetic_cases() -> None:
    result = load_telegram_export(FIXTURE)

    assert result.chat.name == "Synthetic Solutions Fixture"
    assert len(result.messages) == 9
    assert "https://sellerstock.test/demo" in result.messages[3].text
    assert "@StockPilot" in result.messages[4].text
    assert "Рекомендую бот @StockPilot" in result.messages[5].text
    assert "Промокод PARTNER20" in result.messages[6].text
    assert "2500 руб/мес" in result.messages[7].text
    assert "ищем альтернативу" in result.messages[8].text


def test_solution_report_extracts_records_and_trust_signals() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)

        db = Database(db_path)
        try:
            report = build_solution_report(db.messages_for_solutions())
        finally:
            db.close()

    records = {record.identity_key: record for record in report.records}
    assert set(records) == {
        "name:sellerstock",
        "name:stockpilot",
        "name:megaseller",
    }

    sellerstock = records["name:sellerstock"]
    assert sellerstock.primary_subtype == "solution_ad"
    assert sellerstock.subtypes == ("solution_ad",)
    assert sellerstock.solution_type == "analytics_service"
    assert sellerstock.locators == ("https://sellerstock.test/demo",)
    assert sellerstock.promise == "stock_reconciliation"
    assert sellerstock.target_audience == ("marketplace_sellers",)
    assert "owned_solution" in sellerstock.ad_signals
    assert sellerstock.trust_payment_signals == ()
    assert sellerstock.trust_level == "none"
    assert sellerstock.payment_status == "ad_only_unproven"

    stockpilot = records["name:stockpilot"]
    assert stockpilot.primary_subtype == "recommendation"
    assert stockpilot.subtypes == ("recommendation", "solution_ad", "tool_mention")
    assert stockpilot.solution_type == "telegram_bot"
    assert stockpilot.locators == ("@StockPilot",)
    assert stockpilot.price == "2500 руб/мес"
    assert stockpilot.source_message_ids == (
        "3000000000:5",
        "3000000000:6",
        "3000000000:8",
    )
    assert stockpilot.trust_payment_signals == (
        "price_discussion",
        "explicit_paid_subscription",
        "recommendation_from_participant",
        "repeated_independent_mention",
    )
    assert stockpilot.trust_level == "strong"
    assert stockpilot.payment_status == "trust_signals_present"

    megaseller = records["name:megaseller"]
    assert megaseller.primary_subtype == "affiliate_or_spam"
    assert megaseller.subtypes == ("affiliate_or_spam", "solution_ad", "tool_mention")
    assert megaseller.solution_type == "reporting_automation"
    assert megaseller.locators == ("https://megaseller.test/ref?x=1",)
    assert "affiliate_marker" in megaseller.ad_signals
    assert megaseller.trust_payment_signals == (
        "complaint_about_alternative",
    )


def test_solutions_cli_is_privacy_safe_by_default_and_raw_local_is_explicit(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        records = run_solutions(db_path)
        safe_output = capsys.readouterr().out

        run_solutions(db_path, raw_local=True)
        raw_output = capsys.readouterr().out

    assert len(records) == 3
    assert records[0].identity.startswith("solution")
    assert not hasattr(records[0], "name")
    assert not hasattr(records[0], "normalized_text")
    assert not hasattr(records[0].mentions[0], "author")
    assert not hasattr(records[0].mentions[0], "from_id")
    assert not hasattr(records[0].mentions[0], "normalized_text")
    assert "Solutions: 3" in safe_output
    assert "identity=solution" in safe_output
    assert "locators=url" in safe_output
    assert "locators=handle" in safe_output
    assert "source_message_ids=chat1:5,chat1:6,chat1:8" in safe_output
    assert "https://sellerstock.test" not in safe_output
    assert "https://megaseller.test" not in safe_output
    assert "@StockPilot" not in safe_output
    assert "sellerstock.test" not in safe_output
    assert "megaseller.test" not in safe_output
    assert "StockPilot" not in safe_output

    assert "https://sellerstock.test/demo" in raw_output
    assert "https://megaseller.test/ref?x=1" in raw_output
    assert "@StockPilot" in raw_output


def test_solution_signals_do_not_enter_pain_frequency_or_cluster_evidence(
    capsys,
) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        db = Database(db_path)
        try:
            frequencies = {
                row["category"]: dict(row)
                for row in db.deduplicated_label_frequencies()
            }
            report = build_cluster_report(db.messages_for_clustering())
        finally:
            db.close()

        run_clusters(db_path)
        cluster_output = capsys.readouterr().out

    assert frequencies["pain"]["raw_count"] == 3
    assert frequencies["pain"]["unique_count"] == 3
    assert frequencies["solution_ad"]["raw_count"] == 3
    assert frequencies["tool_mention"]["raw_count"] == 2

    stock = {
        cluster.cluster_id: cluster
        for cluster in report.clusters
    }["pain:stock:stock_reconciliation"]
    assert [item.msg_id for item in stock.evidence] == [1, 2, 3]
    assert {item.msg_id for item in stock.rejected} == {4, 5, 6}
    assert "message_id=chat1:4 category=solution_ad" in cluster_output
    assert "message_id=chat1:5 category=tool_mention" in cluster_output
    assert "message_id=chat1:6 category=tool_mention" in cluster_output


def test_plain_ad_price_is_not_payment_trust_signal() -> None:
    report = build_solution_report(
        [
            solution_message(
                1,
                (
                    "Запустили наш сервис PriceBot для селлеров: "
                    "тариф 2500 руб/мес, подписка, демо https://price.test."
                ),
            )
        ]
    )

    record = report.records[0]
    assert "price_visible" in record.ad_signals
    assert "subscription_or_tariff" in record.ad_signals
    assert record.trust_payment_signals == ()
    assert record.trust_level == "none"
    assert record.payment_status == "ad_only_unproven"


def test_repeated_independent_requires_distinct_sources() -> None:
    report = build_solution_report(
        [
            solution_message(
                1,
                "Запустили наш сервис SameTool для отчетов WB: https://same.test/a.",
                author="same_ad_author",
                from_id="same_ad_author",
            ),
            solution_message(
                2,
                "SameTool теперь делает отчеты по Ozon, пишите в лс: https://same.test/b.",
                author="same_ad_author",
                from_id="same_ad_author",
            ),
        ]
    )

    record = report.records[0]
    assert "repeated_independent_mention" not in record.trust_payment_signals
    assert record.payment_status == "ad_only_unproven"


def test_default_solution_output_does_not_print_raw_promise_text(capsys) -> None:
    with temporary_db_path() as db_path:
        db = Database(db_path)
        try:
            chat = ChatRecord(
                chat_id="review_chat",
                name="Synthetic",
                type="public_supergroup",
                total_messages=1,
            )
            text = (
                "Запустили сервис для PrivateChat42 user_id 123456: "
                "сверка остатков."
            )
            message = MessageRecord(
                chat_id="review_chat",
                msg_id=1,
                date="2026-05-19T12:00:00",
                author="synthetic",
                from_id="synthetic",
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
            db.import_chat(chat, [message])
            db.upsert_message_labels(
                [
                    LabelRecord(
                        chat_id="review_chat",
                        msg_id=1,
                        category="solution_ad",
                        topics=["stock"],
                        confidence=1.0,
                        source="rules",
                        classifier_name="review",
                        classifier_version="test",
                        run_id="review-run",
                    )
                ]
            )
        finally:
            db.close()

        run_solutions(db_path)
        output = capsys.readouterr().out

    assert "PrivateChat42" not in output
    assert "user_id" not in output
    assert "123456" not in output
    assert "promise=stock_reconciliation" in output


def test_plain_write_request_is_not_solution_ad() -> None:
    category, topics, _confidence = classify_text(
        "Пишите, у кого сверка остатков не работает: WB показывает одно, в таблице другое."
    )

    assert category == "pain"
    assert "stock" in topics


def test_person_name_complaint_is_not_solution_record() -> None:
    report = build_solution_report(
        [
            solution_message(
                1,
                "Менеджер Alex не работает с выгрузкой, ищем альтернативу.",
                category="offtopic",
            )
        ]
    )

    assert report.records == ()
