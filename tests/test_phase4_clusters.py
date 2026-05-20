from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.cli import _cluster_evidence_ids, run_classify, run_clusters, run_import
from app.clusters import (
    build_cluster_report,
    build_clusters,
    detect_problem_marker_matches,
)
from app.core.models import ClusterSourceMessage
from app.importers.telegram import load_telegram_export
from app.storage.sqlite import Database


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_clusters_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_phase4_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


def test_cluster_fixture_has_required_synthetic_cases() -> None:
    result = load_telegram_export(FIXTURE)

    assert result.chat.name == "Synthetic Cluster Fixture"
    assert len(result.messages) == 10
    assert result.messages[3].text == result.messages[0].text
    assert result.messages[4].forwarded_from == "Synthetic Public Source"
    assert "Запустили наш сервис" in result.messages[7].text
    assert "бот https://example.test/bot" in result.messages[8].text
    assert "прошла нормально" in result.messages[9].text


def test_problem_marker_dictionary_detects_explicit_synonyms() -> None:
    matches = detect_problem_marker_matches(
        "Сверка остатков не работает, а потом надо посчитать маржу."
    )

    marker_keys = {match.marker.key for match in matches}
    assert marker_keys == {"stock_reconciliation", "margin_calculation"}


def test_clusters_count_unique_evidence_and_keep_noise_separate() -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)

        db = Database(db_path)
        try:
            messages = db.messages_for_clustering()
            clusters = build_clusters(messages)
            report = build_cluster_report(messages)
        finally:
            db.close()

    by_id = {cluster.cluster_id: cluster for cluster in clusters}
    assert report.orphan_noise == ()

    stock = by_id["pain:stock:stock_reconciliation"]
    assert stock.support_status == "supported"
    assert stock.raw_count == 5
    assert stock.unique_count == 3
    assert stock.duplicate_count == 2
    assert stock.weaker_evidence_count == 2
    assert [item.msg_id for item in stock.evidence] == [1, 2, 3, 4, 5]
    assert [item.msg_id for item in stock.rejected] == [8, 9, 10]
    assert {item.category for item in stock.rejected} == {
        "solution_ad",
        "tool_mention",
        "offtopic",
    }
    assert stock.evidence[3].is_duplicate is True
    assert stock.evidence[4].is_forwarded is True
    assert stock.evidence[4].is_duplicate is True
    assert "same category, same topic, same explicit problem marker" in stock.merge_reason

    margin = by_id["question:margin:margin_calculation"]
    assert margin.support_status == "weak_signal"
    assert margin.raw_count == 2
    assert margin.unique_count == 2
    assert margin.duplicate_count == 0
    assert margin.weaker_evidence_count == 0
    assert [item.msg_id for item in margin.evidence] == [6, 7]

    assert all(
        not cluster.cluster_id.startswith("solution_ad:")
        and not cluster.cluster_id.startswith("tool_mention:")
        for cluster in clusters
    )


def test_clusters_cli_explains_evidence_and_rejections(capsys) -> None:
    with temporary_db_path() as db_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        clusters = run_clusters(db_path)
        output = capsys.readouterr().out

    assert len(clusters) == 2
    assert "pain:stock:stock_reconciliation [supported]" in output
    assert (
        "raw_count=5 unique_count=3 duplicate_count=2 "
        "weaker_evidence_count=2"
    ) in output
    assert (
        "evidence_message_ids="
        "chat1:1,chat1:2,chat1:3,chat1:4,chat1:5"
    ) in output
    assert (
        "rejected/noise_message_ids="
        "chat1:8,chat1:9,chat1:10"
    ) in output
    assert (
        "message_id=chat1:5 match=сверка остатков "
        "evidence=forwarded,duplicate"
    ) in output
    assert "message_id=chat1:8 category=solution_ad" in output
    assert "message_id=chat1:9 category=tool_mention" in output
    assert "message_id=chat1:10 category=offtopic" in output
    assert "question:margin:margin_calculation [weak_signal]" in output
    assert "evidence_message_ids=chat1:6,chat1:7" in output
    assert "2000000000:" not in output
    assert "reason=same category, same topic, same explicit problem marker" in output


def test_cli_evidence_ids_stay_stable_across_chats() -> None:
    messages = [
        ClusterSourceMessage(
            chat_id="chat_a",
            msg_id=1,
            date="2026-05-19T10:00:00",
            category="pain",
            topics=("stock",),
            text="Не могу свести остатки WB и Ozon вручную.",
            normalized_text="не могу свести остатки wb и ozon вручную.",
            forwarded_from="",
        ),
        ClusterSourceMessage(
            chat_id="chat_b",
            msg_id=1,
            date="2026-05-19T10:01:00",
            category="pain",
            topics=("stock",),
            text="Сверка остатков не работает, в таблице другое.",
            normalized_text="сверка остатков не работает, в таблице другое.",
            forwarded_from="",
        ),
        ClusterSourceMessage(
            chat_id="chat_c",
            msg_id=2,
            date="2026-05-19T10:02:00",
            category="pain",
            topics=("stock",),
            text="Расхождение остатков после поставки, всё делаю вручную.",
            normalized_text="расхождение остатков после поставки, всё делаю вручную.",
            forwarded_from="",
        ),
    ]
    cluster = build_clusters(messages)[0]
    chat_aliases = {"chat_a": "chat1", "chat_b": "chat2", "chat_c": "chat3"}

    assert cluster.evidence_message_ids == ("chat_a:1", "chat_b:1", "chat_c:2")
    assert (
        _cluster_evidence_ids(cluster, chat_aliases, raw_local=True)
        == "chat_a:1,chat_b:1,chat_c:2"
    )
    assert (
        _cluster_evidence_ids(cluster, chat_aliases, raw_local=False)
        == "chat1:1,chat2:1,chat3:2"
    )


def test_noise_only_problem_markers_are_reported_without_cluster() -> None:
    report = build_cluster_report(
        [
            ClusterSourceMessage(
                chat_id="chat",
                msg_id=8,
                date="2026-05-19T10:00:00",
                category="solution_ad",
                topics=("stock", "automation"),
                text=(
                    "Запустили наш сервис для сверки остатков WB и Ozon: "
                    "демо на https://example.test."
                ),
                normalized_text=(
                    "запустили наш сервис для сверки остатков wb и ozon <url>"
                ),
                forwarded_from="",
            ),
            ClusterSourceMessage(
                chat_id="chat",
                msg_id=9,
                date="2026-05-19T10:01:00",
                category="tool_mention",
                topics=("stock", "automation"),
                text="Кто пробовал бот https://example.test/bot для сверки остатков?",
                normalized_text="кто пробовал бот <url> для сверки остатков?",
                forwarded_from="",
            ),
        ]
    )

    assert report.clusters == ()
    assert len(report.orphan_noise) == 1
    noise_group = report.orphan_noise[0]
    assert noise_group.topic == "stock"
    assert noise_group.problem_marker == "stock_reconciliation"
    assert noise_group.rejected_message_ids == ("chat:8", "chat:9")
    assert [item.category for item in noise_group.rejected] == [
        "solution_ad",
        "tool_mention",
    ]
