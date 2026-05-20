from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.cli import run_classify, run_import, run_opportunities
from app.core.models import ClusterEvidence, ClusterRecord, SolutionRecord
from app.opportunities import (
    MAX_OPPORTUNITY_CARDS,
    OpportunityCard,
    build_opportunity_cards,
)


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_solutions_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_phase6_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


def make_cluster(
    texts: tuple[str, ...],
    *,
    marker: str = "stock_reconciliation",
    topic: str = "stock",
    label: str = "stock reconciliation mismatch",
    unique_count: int | None = None,
    weaker_evidence_count: int = 0,
    support_status: str | None = None,
) -> ClusterRecord:
    evidence = tuple(
        ClusterEvidence(
            chat_id="chat",
            msg_id=index,
            message_ref=f"chat:{index}",
            evidence_key=text if unique_count != 1 else "same-evidence",
            matched_synonym="сверка остатков",
            is_forwarded=index <= weaker_evidence_count,
            is_duplicate=False,
            normalized_text=text,
        )
        for index, text in enumerate(texts, start=1)
    )
    resolved_unique_count = unique_count if unique_count is not None else len(texts)
    resolved_support_status = (
        support_status
        if support_status is not None
        else ("supported" if resolved_unique_count >= 3 else "weak_signal")
    )
    return ClusterRecord(
        cluster_id=f"pain:{topic}:{marker}",
        category="pain",
        topic=topic,
        problem_marker=marker,
        problem_label=label,
        raw_count=len(texts),
        unique_count=resolved_unique_count,
        duplicate_count=max(0, len(texts) - resolved_unique_count),
        weaker_evidence_count=weaker_evidence_count,
        support_status=resolved_support_status,
        evidence_message_ids=tuple(item.message_ref for item in evidence),
        rejected_message_ids=(),
        merge_reason="same category, same topic, same explicit problem marker",
        evidence=evidence,
        rejected=(),
    )


def make_solution(
    *,
    solution_id: str = "solution1",
    payment_status: str = "ad_only_unproven",
    trust_payment_signals: tuple[str, ...] = (),
    source_message_ids: tuple[str, ...] = ("chat:10",),
    target_audience: tuple[str, ...] = (),
) -> SolutionRecord:
    return SolutionRecord(
        solution_id=solution_id,
        identity_key=f"name:{solution_id}",
        primary_subtype="solution_ad",
        subtypes=("solution_ad",),
        solution_type="analytics_service",
        name=solution_id,
        locators=("https://private.test/demo", "@PrivateTool"),
        promise="stock_reconciliation",
        target_audience=target_audience,
        ad_signals=("price_visible", "subscription_or_tariff"),
        price="2500 руб/мес",
        source_message_ids=source_message_ids,
        trust_payment_signals=trust_payment_signals,
        trust_level="strong" if trust_payment_signals else "none",
        payment_status=payment_status,
        mentions=(),
    )


def evidence_fields(card: OpportunityCard) -> set[str]:
    return {item.field for item in card.evidence}


def test_card_uses_unknown_instead_of_fantasizing_missing_fields() -> None:
    cluster = make_cluster(
        (
            "сверка остатков не работает",
            "остатки не сходятся после поставки",
        ),
        unique_count=2,
        support_status="weak_signal",
    )

    card = build_opportunity_cards((cluster,), ())[0]

    assert card.problem == "stock reconciliation mismatch"
    assert card.frequency.startswith("unique_count=2")
    assert card.audience == "unknown"
    assert card.current_workaround == "unknown"
    assert card.ready_solutions == "unknown"
    assert card.first_mvp == "unknown"
    assert card.payment_reason == "unknown"

    fields = evidence_fields(card)
    assert "problem" in fields
    assert "frequency" in fields
    assert "audience" not in fields
    assert "current_workaround" not in fields
    assert "ready_solutions" not in fields
    assert "first_mvp" not in fields
    assert "payment_reason" not in fields


def test_ad_only_solution_does_not_create_payment_reason_by_itself() -> None:
    cluster = make_cluster(
        (
            "сверка остатков не работает",
            "остатки не сходятся после поставки",
            "не могу сверить остатки wb и ozon",
        )
    )
    ad_only = make_solution(
        payment_status="ad_only_unproven",
        target_audience=("marketplace_managers",),
    )

    card = build_opportunity_cards((cluster,), (ad_only,))[0]

    assert "ad_only_unproven" in card.ready_solutions
    assert card.payment_reason == "unknown"
    assert card.score.willingness_to_pay == 1
    assert "payment_reason" not in evidence_fields(card)


def test_builder_rejects_non_positive_limit() -> None:
    cluster = make_cluster(("сверка остатков не работает",), unique_count=1)

    try:
        build_opportunity_cards((cluster,), (), limit=0)
    except ValueError as exc:
        assert "limit must be greater than 0" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("limit=0 must be rejected")

    try:
        build_opportunity_cards((cluster,), (), limit=-1)
    except ValueError as exc:
        assert "limit must be greater than 0" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("negative limit must be rejected")


def test_builder_rejects_excessive_limit() -> None:
    cluster = make_cluster(("сверка остатков не работает",), unique_count=1)

    try:
        build_opportunity_cards((cluster,), (), limit=MAX_OPPORTUNITY_CARDS + 1)
    except ValueError as exc:
        assert f"limit must be <= {MAX_OPPORTUNITY_CARDS}" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("excessive limit must be rejected")


def test_cli_rejects_excessive_opportunity_limit() -> None:
    with temporary_db_path() as db_path:
        try:
            run_opportunities(db_path, limit=MAX_OPPORTUNITY_CARDS + 1)
        except ValueError as exc:
            assert f"--limit must be <= {MAX_OPPORTUNITY_CARDS}" in str(exc)
        else:  # pragma: no cover - failure path
            raise AssertionError("excessive CLI limit must be rejected")


def test_payment_reason_uses_only_allowed_evidence_signals() -> None:
    cluster = make_cluster(
        (
            "вручную уходит два часа сверка остатков",
            "каждый раз расхождение остатков после поставки",
            "сверка остатков не работает",
        )
    )
    trusted_solution = make_solution(
        payment_status="trust_signals_present",
        trust_payment_signals=(
            "price_discussion",
            "explicit_paid_subscription",
        ),
        source_message_ids=("chat:20", "chat:21"),
        target_audience=("marketplace_managers",),
    )

    card = build_opportunity_cards((cluster,), (trusted_solution,))[0]

    assert card.payment_reason == (
        "solution_trust_payment_signals,"
        "time_or_money_loss,"
        "repeated_workflow,"
        "manager_agency_client_reporting_scenario"
    )
    payment_evidence = [
        item for item in card.evidence if item.field == "payment_reason"
    ]
    assert {item.label for item in payment_evidence} == {
        "payment:explicit_paid_subscription,price_discussion",
        "payment:time_or_money_loss",
        "payment:repeated_workflow",
        "payment:manager_agency_client_reporting",
    }


def test_score_frequency_uses_unique_count_not_raw_count() -> None:
    repeated_cluster = make_cluster(
        tuple("сверка остатков не работает" for _ in range(10)),
        unique_count=1,
        support_status="weak_signal",
    )
    unique_cluster = make_cluster(
        (
            "сверка остатков не работает",
            "не могу сверить остатки",
            "остатки не сходятся после поставки",
        ),
        unique_count=3,
        support_status="supported",
    )

    unique_card, repeated_card = build_opportunity_cards(
        (repeated_cluster, unique_cluster),
        (),
        limit=2,
    )

    assert unique_card.score.frequency == 3
    assert repeated_card.score.frequency == 1
    assert unique_card.score.total > repeated_card.score.total


def test_weaker_evidence_lowers_confidence_scores() -> None:
    strong_cluster = make_cluster(
        (
            "вручную уходит два часа сверка остатков",
            "каждый раз расхождение остатков после поставки",
            "сверка остатков не работает",
        )
    )
    weak_evidence_cluster = make_cluster(
        (
            "вручную уходит два часа сверка остатков",
            "каждый раз расхождение остатков после поставки",
            "сверка остатков не работает",
        ),
        weaker_evidence_count=1,
    )

    strong_card, weak_card = build_opportunity_cards(
        (strong_cluster, weak_evidence_cluster),
        (),
        limit=2,
    )

    assert strong_card.score.urgency > weak_card.score.urgency
    assert strong_card.score.repeatability > weak_card.score.repeatability
    assert "weaker_evidence_count=1" in weak_card.frequency


def test_top_cards_are_sorted_by_score() -> None:
    weak = make_cluster(("сверка остатков не работает",), unique_count=1)
    medium = make_cluster(
        (
            "сверка остатков не работает",
            "не могу сверить остатки",
            "остатки не сходятся после поставки",
        ),
        unique_count=3,
    )
    strong = make_cluster(
        (
            "вручную уходит два часа сверка остатков",
            "каждый раз расхождение остатков после поставки",
            "сверка остатков не работает",
            "не могу сверить остатки",
            "остатки по складам расходятся",
            "сверка остатков вручную",
        ),
        unique_count=6,
    )

    cards = build_opportunity_cards((weak, medium, strong), (), limit=3)
    totals = [card.score.total for card in cards]

    assert totals == sorted(totals, reverse=True)
    assert [card.opportunity_id for card in cards] == [
        "opportunity1",
        "opportunity2",
        "opportunity3",
    ]
    assert cards[0].frequency.startswith("unique_count=6")


def test_opportunities_cli_is_safe_by_default_and_prints_evidence(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        cards = run_opportunities(db_path)
        output = capsys.readouterr().out

    assert len(cards) == 1
    assert "Opportunities: 1" in output
    assert "problem=stock reconciliation mismatch" in output
    assert "frequency=unique_count=3; raw_count=3" in output
    assert "current_workaround=manual_spreadsheet_or_cabinet_reconciliation" in output
    assert "payment_reason=solution_trust_payment_signals" in output
    assert "field=problem source_message_ids=chat1:1,chat1:2,chat1:3" in output
    assert "field=score source_message_ids=chat1:1,chat1:2,chat1:3" in output
    assert "https://sellerstock.test" not in output
    assert "https://megaseller.test" not in output
    assert "@StockPilot" not in output
    assert "synthetic_participant" not in output
    assert "Не могу свести" not in output
    assert "Рекомендую бот" not in output
