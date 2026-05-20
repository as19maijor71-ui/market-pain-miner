from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from app.classifiers.rules import CLASSIFIER_NAME, CLASSIFIER_VERSION, classify_text
from app.classifiers.taxonomy import MESSAGE_CATEGORIES, PAIN_TOPICS
from app.clusters import build_cluster_report
from app.core.models import (
    ClusterNoiseGroup,
    ClusterRecord,
    LabelRecord,
    SolutionRecord,
)
from app.importers.telegram import load_telegram_export
from app.opportunities import (
    MAX_OPPORTUNITY_CARDS,
    OpportunityCard,
    build_opportunity_cards,
)
from app.solutions import build_solution_report
from app.storage.sqlite import Database


DEFAULT_DB = Path("data/db/chatkb.sqlite")
DEFAULT_EXPECTED_LABELS = Path("tests/fixtures/telegram_expected_labels.json")
KEY_EVALUATION_CATEGORIES = ("pain", "question", "solution_ad", "tool_mention")
KEY_FREQUENCY_CATEGORIES = ("pain", "question", "solution_ad", "tool_mention")
PRIVATE_DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
MAX_LATEST = 100
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
MANUAL_CLASSIFIER_NAME = "manual_review"
MANUAL_CLASSIFIER_VERSION = "2026-05-19.1"
REVIEW_CONFIDENCE_THRESHOLD = 0.55
REVIEW_DEFAULT_LIMIT = 20
HIGH_RISK_MARKERS = (
    "api_access",
    "legal",
    "limited_access",
    "uncertainty",
    "policy",
)


@dataclass(frozen=True)
class SolutionDisplayMention:
    message_id: str
    category: str
    subtype: str
    flags: str


@dataclass(frozen=True)
class SolutionDisplayRecord:
    solution_id: str
    primary_subtype: str
    trust_level: str
    payment_status: str
    subtypes: str
    solution_type: str
    identity: str
    locators: str
    promise: str
    target_audience: str
    price: str
    ad_signals: str
    trust_payment_signals: str
    source_message_ids: str
    mentions: tuple[SolutionDisplayMention, ...]


@dataclass(frozen=True)
class ManualCorrectionImpact:
    evaluate_fixed_error: bool
    evaluate_introduced_error: bool
    opportunity_changed: bool
    opportunity_changes: tuple[str, ...]

    @property
    def allows_write(self) -> bool:
        if self.evaluate_introduced_error:
            return False
        return self.evaluate_fixed_error or self.opportunity_changed

    @property
    def summary(self) -> str:
        values = []
        if self.evaluate_fixed_error:
            values.append("evaluate_fixed_error")
        if self.evaluate_introduced_error:
            values.append("evaluate_introduced_error")
        if self.opportunity_changed:
            values.append("opportunity_changed")
        if not values:
            values.append("none")
        return ",".join(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Pain Miner CLI")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite database")
    parser.add_argument(
        "--allow-external-db",
        action="store_true",
        help=(
            "Unsafe local-only: allow writing private Telegram data outside "
            "data/db or test temp DB paths"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import Telegram Desktop result.json")
    import_parser.add_argument("result_json", help="Path to Telegram result.json")

    classify_parser = subparsers.add_parser(
        "classify",
        help="Classify imported messages with rule-based labels",
    )
    classify_parser.add_argument(
        "--classifier-name",
        default=CLASSIFIER_NAME,
        help=f"Classifier name to store, default: {CLASSIFIER_NAME}",
    )
    classify_parser.add_argument(
        "--classifier-version",
        default=CLASSIFIER_VERSION,
        help=f"Classifier version to store, default: {CLASSIFIER_VERSION}",
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Evaluate classifier labels against a manual control sample",
    )
    evaluate_parser.add_argument(
        "--expected",
        default=str(DEFAULT_EXPECTED_LABELS),
        help="Path to expected labels JSON",
    )
    evaluate_parser.add_argument(
        "--classifier-name",
        default=CLASSIFIER_NAME,
        help=f"Classifier name to evaluate, default: {CLASSIFIER_NAME}",
    )
    evaluate_parser.add_argument(
        "--classifier-version",
        default=CLASSIFIER_VERSION,
        help=f"Classifier version to evaluate, default: {CLASSIFIER_VERSION}",
    )
    evaluate_parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run_id to evaluate. Defaults to latest matching run.",
    )

    review_parser = subparsers.add_parser(
        "review",
        aliases=["review-candidates"],
        help="Show review candidates and store narrow manual label corrections",
    )
    review_parser.add_argument(
        "--limit",
        type=int,
        default=REVIEW_DEFAULT_LIMIT,
        help=f"Max items per review section, default: {REVIEW_DEFAULT_LIMIT}",
    )
    review_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=REVIEW_CONFIDENCE_THRESHOLD,
        help=(
            "Labels at or below this confidence are shown as review candidates; "
            f"default: {REVIEW_CONFIDENCE_THRESHOLD}"
        ),
    )
    review_parser.add_argument(
        "--set-label",
        nargs=2,
        metavar=("MESSAGE_ID", "CATEGORY"),
        help=(
            "Store one manual label correction, e.g. "
            "'--set-label chat1:6 pain'. MESSAGE_ID may be chat alias, "
            "raw chat_id, or a bare msg_id if unique."
        ),
    )
    review_parser.add_argument(
        "--expected",
        default=str(DEFAULT_EXPECTED_LABELS),
        help=(
            "Expected labels JSON used to prove evaluate impact for "
            "--set-label; default: tests fixture control sample"
        ),
    )
    review_parser.add_argument(
        "--topics",
        default=None,
        help=(
            "Comma-separated topics for --set-label. Defaults to current "
            "effective topics."
        ),
    )
    review_parser.add_argument(
        "--classifier-name",
        default=MANUAL_CLASSIFIER_NAME,
        help=f"Manual classifier name, default: {MANUAL_CLASSIFIER_NAME}",
    )
    review_parser.add_argument(
        "--classifier-version",
        default=MANUAL_CLASSIFIER_VERSION,
        help=f"Manual classifier version, default: {MANUAL_CLASSIFIER_VERSION}",
    )
    review_parser.add_argument(
        "--run-id",
        default=None,
        help="Optional manual run_id. Defaults to a fresh UUID.",
    )
    review_parser.add_argument(
        "--raw-local",
        action="store_true",
        help="Unsafe local-only: show raw chat ids and message previews",
    )

    summary_parser = subparsers.add_parser(
        "summary",
        help="Show one privacy-safe research run summary",
    )
    summary_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help=f"Max items per summary section, 1-{MAX_OPPORTUNITY_CARDS}; default: 5",
    )
    summary_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=REVIEW_CONFIDENCE_THRESHOLD,
        help=(
            "Labels at or below this confidence are counted as review candidates; "
            f"default: {REVIEW_CONFIDENCE_THRESHOLD}"
        ),
    )

    stats_parser = subparsers.add_parser("stats", help="Show database stats")
    stats_parser.add_argument(
        "--latest",
        type=parse_latest_limit,
        default=0,
        help=f"Show latest N messages, 0-{MAX_LATEST}",
    )
    stats_parser.add_argument(
        "--raw-local",
        action="store_true",
        help="Unsafe local-only: show raw authors and message previews",
    )

    clusters_parser = subparsers.add_parser(
        "clusters",
        help="Show explicit pain/question clusters from active labels",
    )
    clusters_parser.add_argument(
        "--raw-local",
        action="store_true",
        help=(
            "Unsafe local-only: show raw chat ids and normalized evidence text "
            "for debugging"
        ),
    )

    solutions_parser = subparsers.add_parser(
        "solutions",
        help="Show solution and competitor mentions from active labels",
    )
    solutions_parser.add_argument(
        "--raw-local",
        action="store_true",
        help="Unsafe local-only: show raw solution URLs and Telegram handles",
    )

    opportunities_parser = subparsers.add_parser(
        "opportunities",
        help="Show top evidence-backed product opportunity cards",
    )
    opportunities_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help=f"Number of top cards to show, 1-{MAX_OPPORTUNITY_CARDS}; default: 5",
    )
    opportunities_parser.add_argument(
        "--raw-local",
        action="store_true",
        help="Unsafe local-only: show raw chat ids in evidence message ids",
    )

    args = parser.parse_args()

    try:
        if args.command == "import":
            run_import(
                Path(args.result_json),
                Path(args.db),
                allow_external_db=args.allow_external_db,
            )
        elif args.command == "classify":
            run_classify(
                Path(args.db),
                classifier_name=args.classifier_name,
                classifier_version=args.classifier_version,
                allow_external_db=args.allow_external_db,
            )
        elif args.command == "evaluate":
            run_evaluate(
                Path(args.db),
                Path(args.expected),
                classifier_name=args.classifier_name,
                classifier_version=args.classifier_version,
                run_id=args.run_id,
                allow_external_db=args.allow_external_db,
            )
        elif args.command in {"review", "review-candidates"}:
            run_review(
                Path(args.db),
                limit=args.limit,
                confidence_threshold=args.confidence_threshold,
                set_label=tuple(args.set_label) if args.set_label else None,
                expected_path=Path(args.expected),
                topics=args.topics,
                classifier_name=args.classifier_name,
                classifier_version=args.classifier_version,
                run_id=args.run_id,
                raw_local=args.raw_local,
                allow_external_db=args.allow_external_db,
            )
        elif args.command == "summary":
            run_summary(
                Path(args.db),
                limit=args.limit,
                confidence_threshold=args.confidence_threshold,
                allow_external_db=args.allow_external_db,
            )
        elif args.command == "stats":
            run_stats(
                Path(args.db),
                latest=args.latest,
                raw_local=args.raw_local,
                allow_external_db=args.allow_external_db,
            )
        elif args.command == "clusters":
            run_clusters(
                Path(args.db),
                raw_local=args.raw_local,
                allow_external_db=args.allow_external_db,
            )
        elif args.command == "solutions":
            run_solutions(
                Path(args.db),
                raw_local=args.raw_local,
                allow_external_db=args.allow_external_db,
            )
        elif args.command == "opportunities":
            run_opportunities(
                Path(args.db),
                limit=args.limit,
                raw_local=args.raw_local,
                allow_external_db=args.allow_external_db,
            )
    except ValueError as exc:
        parser.exit(1, f"Error: {terminal_safe(exc)}\n")


def run_import(
    result_json: Path,
    db_path: Path,
    *,
    allow_external_db: bool = False,
) -> None:
    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    imported = load_telegram_export(result_json)
    db = Database(db_path)
    try:
        changed = db.import_chat(imported.chat, imported.messages)
    finally:
        db.close()

    print("Imported chats: 1")
    print(f"Messages in export: {len(imported.messages)}")
    print(f"Rows inserted/updated: {changed}")
    print(f"Database: {terminal_safe(db_path)}")


def run_classify(
    db_path: Path,
    *,
    classifier_name: str = CLASSIFIER_NAME,
    classifier_version: str = CLASSIFIER_VERSION,
    allow_external_db: bool = False,
) -> str:
    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    run_id = uuid4().hex
    db = Database(db_path)
    try:
        messages = db.messages_for_classification()
        labels = []
        for row in messages:
            category, topics, confidence = classify_text(str(row["text"]))
            labels.append(
                LabelRecord(
                    chat_id=str(row["chat_id"]),
                    msg_id=int(row["msg_id"]),
                    category=category,
                    topics=topics,
                    confidence=confidence,
                    source="rules",
                    classifier_name=classifier_name,
                    classifier_version=classifier_version,
                    run_id=run_id,
                )
            )
        changed = db.upsert_message_labels(labels)
    finally:
        db.close()

    print(f"Messages scanned: {len(messages)}")
    print(f"Labels inserted/updated: {changed}")
    print(f"Classifier: {terminal_safe(classifier_name)} {terminal_safe(classifier_version)}")
    print(f"Run ID: {terminal_safe(run_id)}")
    print(f"Database: {terminal_safe(db_path)}")
    return run_id


def run_stats(
    db_path: Path,
    latest: int = 0,
    raw_local: bool = False,
    *,
    allow_external_db: bool = False,
) -> None:
    latest = validate_latest_limit(latest)
    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    db = Database(db_path)
    try:
        stats = db.stats()
        print(f"Chats: {stats['chats']}")
        print(f"Messages: {stats['messages']}")
        print(f"Labels: {stats['labels']}")
        print(f"Unclassified messages: {stats['unclassified']}")

        versions = db.label_versions()
        if versions:
            print("")
            print("Label versions:")
            for row in versions:
                print(
                    "- "
                    f"{terminal_safe(row['source'])}/"
                    f"{terminal_safe(row['classifier_name'])} "
                    f"{terminal_safe(row['classifier_version'])} "
                    f"run {terminal_safe(row['run_id'])}: "
                    f"{row['count']} labels"
                )

        active_run = db.latest_classifier_run()
        if active_run is not None:
            print("")
            print(
                "Active classifier: "
                f"{terminal_safe(active_run['classifier_name'])} "
                f"{terminal_safe(active_run['classifier_version'])} "
                f"run {terminal_safe(active_run['run_id'])}"
            )

        distribution = db.label_distribution()
        if distribution:
            print("")
            print("Category distribution (active labels):")
            for row in distribution:
                print(f"- {row['category']}: {row['count']}")

        frequencies = db.deduplicated_label_frequencies(KEY_FREQUENCY_CATEGORIES)
        if frequencies:
            print("")
            print("Deduplicated frequencies (active labels; scoring uses unique_count):")
            for row in frequencies:
                print(
                    "- "
                    f"{terminal_safe(row['category'])}: "
                    f"raw_count={row['raw_count']} "
                    f"unique_count={row['unique_count']} "
                    f"duplicate_count={row['duplicate_count']} "
                    f"weaker_evidence_count={row['weaker_evidence_count']} "
                    f"scoring_count={row['unique_count']}"
                )

        duplicate_groups = db.duplicate_label_groups(KEY_FREQUENCY_CATEGORIES)
        if duplicate_groups:
            print("")
            print("Exact duplicate groups:")
            for group_index, row in enumerate(duplicate_groups, start=1):
                print(
                    "- "
                    f"{terminal_safe(row['category'])}: "
                    f"duplicate_group={group_index} "
                    f"raw_count={row['raw_count']} "
                    f"duplicate_count={row['duplicate_count']} "
                    f"messages={terminal_safe(row['msg_ids'])}"
                )

        weak_evidence = db.weak_evidence_messages(KEY_FREQUENCY_CATEGORIES)
        if weak_evidence:
            print("")
            print("Weaker evidence messages (forwarded/repeated):")
            for row in weak_evidence:
                reasons = []
                if row["is_forwarded"]:
                    reasons.append("forwarded")
                if row["is_repeated"]:
                    reasons.append("repeated")
                print(
                    "- "
                    f"{terminal_safe(row['category'])} "
                    f"msg_id={row['msg_id']} "
                    f"reason={terminal_safe(','.join(reasons))}"
                )

        if latest:
            print("")
            print(f"Latest {latest} messages:")
            for index, row in enumerate(db.latest_messages(latest), start=1):
                date = terminal_safe(row["date"])
                category = terminal_safe(row["category"])
                if raw_local:
                    preview = terminal_safe(row["preview"])
                    author = terminal_safe(row["author"])
                    print(
                        f"- {date} #{row['msg_id']} "
                        f"[{category}] {author}: {preview}"
                    )
                else:
                    print(f"- item {index}: {date} [{category}]")
    finally:
        db.close()


def run_clusters(
    db_path: Path,
    raw_local: bool = False,
    *,
    allow_external_db: bool = False,
) -> list[ClusterRecord]:
    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    db = Database(db_path)
    try:
        report = build_cluster_report(db.messages_for_clustering())
    finally:
        db.close()

    clusters = list(report.clusters)
    chat_aliases = _cluster_chat_aliases(clusters, list(report.orphan_noise))
    print(f"Clusters: {len(clusters)}")
    if not clusters and not report.orphan_noise:
        print("- none")
        return clusters

    for cluster in clusters:
        print("")
        print(
            "- "
            f"{terminal_safe(cluster.cluster_id)} "
            f"[{terminal_safe(cluster.support_status)}]"
        )
        print(
            "  "
            f"category={terminal_safe(cluster.category)} "
            f"topic={terminal_safe(cluster.topic)} "
            f"problem_marker={terminal_safe(cluster.problem_marker)}"
        )
        print(
            "  "
            f"raw_count={cluster.raw_count} "
            f"unique_count={cluster.unique_count} "
            f"duplicate_count={cluster.duplicate_count} "
            f"weaker_evidence_count={cluster.weaker_evidence_count}"
        )
        print(
            "  "
            "evidence_message_ids="
            f"{terminal_safe(_cluster_evidence_ids(cluster, chat_aliases, raw_local))}"
        )
        rejected_ids = _cluster_rejected_ids(cluster, chat_aliases, raw_local)
        if rejected_ids:
            print(
                "  "
                "rejected/noise_message_ids="
                f"{terminal_safe(rejected_ids)}"
            )
        else:
            print("  rejected/noise_message_ids=none")
        print(f"  reason={terminal_safe(cluster.merge_reason)}")
        print("  evidence:")
        for item in cluster.evidence:
            weak_reasons = []
            if item.is_forwarded:
                weak_reasons.append("forwarded")
            if item.is_duplicate:
                weak_reasons.append("duplicate")
            weak_text = ",".join(weak_reasons) if weak_reasons else "strong"
            line = (
                "    - "
                f"message_id={terminal_safe(_message_display_id(item, chat_aliases, raw_local))} "
                f"match={terminal_safe(item.matched_synonym)} "
                f"evidence={terminal_safe(weak_text)}"
            )
            if raw_local:
                line += f" normalized_text={terminal_safe(item.normalized_text)}"
            print(line)
        if cluster.rejected:
            print("  rejected/noise:")
            for item in cluster.rejected:
                print(
                    "    - "
                    f"message_id={terminal_safe(_message_display_id(item, chat_aliases, raw_local))} "
                    f"category={terminal_safe(item.category)} "
                    f"match={terminal_safe(item.matched_synonym)} "
                    f"reason={terminal_safe(item.reason)}"
                )

    if report.orphan_noise:
        print("")
        print(f"Rejected/noise without cluster: {len(report.orphan_noise)}")
        for group in report.orphan_noise:
            print(
                "- "
                f"topic={terminal_safe(group.topic)} "
                f"problem_marker={terminal_safe(group.problem_marker)} "
                "rejected/noise_message_ids="
                f"{terminal_safe(_noise_group_rejected_ids(group, chat_aliases, raw_local))}"
            )
            for item in group.rejected:
                print(
                    "  - "
                    f"message_id={terminal_safe(_message_display_id(item, chat_aliases, raw_local))} "
                    f"category={terminal_safe(item.category)} "
                    f"match={terminal_safe(item.matched_synonym)} "
                    f"reason={terminal_safe(item.reason)}"
                )

    return clusters


def run_solutions(
    db_path: Path,
    raw_local: bool = False,
    *,
    allow_external_db: bool = False,
) -> list[SolutionDisplayRecord]:
    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    db = Database(db_path)
    try:
        report = build_solution_report(db.messages_for_solutions())
    finally:
        db.close()

    records = list(report.records)
    chat_aliases = _solution_chat_aliases(records)
    locator_aliases = _solution_locator_aliases(records)

    display_records = _solution_display_records(
        records,
        chat_aliases,
        locator_aliases,
        raw_local,
    )

    print(f"Solutions: {len(display_records)}")
    if not display_records:
        print("- none")
        return []

    for record in display_records:
        print("")
        print(
            "- "
            f"{terminal_safe(record.solution_id)} "
            f"[{terminal_safe(record.primary_subtype)}] "
            f"trust_level={terminal_safe(record.trust_level)} "
            f"payment_status={terminal_safe(record.payment_status)}"
        )
        print(
            "  "
            f"subtypes={terminal_safe(record.subtypes)} "
            f"solution_type={terminal_safe(record.solution_type)}"
        )
        print(
            "  "
            f"identity={terminal_safe(record.identity)} "
            "locators="
            f"{terminal_safe(record.locators)}"
        )
        print(
            "  "
            f"promise={terminal_safe(record.promise)}"
        )
        print(
            "  "
            "target_audience="
            f"{terminal_safe(record.target_audience)} "
            f"price={terminal_safe(record.price)}"
        )
        print(
            "  "
            f"ad_signals={terminal_safe(record.ad_signals)}"
        )
        print(
            "  "
            "trust/payment_signals="
            f"{terminal_safe(record.trust_payment_signals)}"
        )
        print(
            "  "
            "source_message_ids="
            f"{terminal_safe(record.source_message_ids)}"
        )
        print("  mentions:")
        for mention in record.mentions:
            print(
                "    - "
                f"message_id={terminal_safe(mention.message_id)} "
                f"category={terminal_safe(mention.category)} "
                f"subtype={terminal_safe(mention.subtype)} "
                f"flags={terminal_safe(mention.flags)}"
            )

    return list(display_records)


def run_opportunities(
    db_path: Path,
    limit: int = 5,
    raw_local: bool = False,
    *,
    allow_external_db: bool = False,
) -> list[OpportunityCard]:
    if limit <= 0:
        raise ValueError("--limit must be greater than 0")
    if limit > MAX_OPPORTUNITY_CARDS:
        raise ValueError(f"--limit must be <= {MAX_OPPORTUNITY_CARDS}")

    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    db = Database(db_path)
    try:
        cluster_report = build_cluster_report(db.messages_for_clustering())
        solution_report = build_solution_report(db.messages_for_solutions())
    finally:
        db.close()

    cards = list(
        build_opportunity_cards(
            cluster_report.clusters,
            solution_report.records,
            limit=limit,
        )
    )
    chat_aliases = _opportunity_chat_aliases(cards)

    print(f"Opportunities: {len(cards)}")
    if not cards:
        print("- none")
        return []

    for card in cards:
        print("")
        print(
            "- "
            f"{terminal_safe(card.opportunity_id)} "
            f"[{terminal_safe(card.support_status)}] "
            f"score={card.score.total} "
            f"verdict={terminal_safe(card.score.verdict)}"
        )
        print(f"  cluster_id={terminal_safe(card.cluster_id)}")
        print(f"  problem={terminal_safe(card.problem)}")
        print(f"  audience={terminal_safe(card.audience)}")
        print(f"  frequency={terminal_safe(card.frequency)}")
        print(f"  current_workaround={terminal_safe(card.current_workaround)}")
        print(f"  ready_solutions={terminal_safe(card.ready_solutions)}")
        print(f"  first_mvp={terminal_safe(card.first_mvp)}")
        print(f"  payment_reason={terminal_safe(card.payment_reason)}")
        print(f"  complexity={terminal_safe(card.complexity)}")
        print(f"  risk={terminal_safe(card.risk)}")
        print(
            "  "
            "score_breakdown="
            f"frequency:{card.score.frequency},"
            f"urgency:{card.score.urgency},"
            f"willingness_to_pay:{card.score.willingness_to_pay},"
            f"mvp_speed:{card.score.mvp_speed},"
            f"repeatability:{card.score.repeatability},"
            f"defensibility:{card.score.defensibility},"
            f"data_access:{card.score.data_access}"
        )
        print("  evidence:")
        for item in card.evidence:
            print(
                "    - "
                f"field={terminal_safe(item.field)} "
                "source_message_ids="
                f"{terminal_safe(_opportunity_source_ids(item.source_message_ids, chat_aliases, raw_local))} "
                f"label={terminal_safe(item.label)} "
                f"reason={terminal_safe(item.reason)}"
            )

    return cards


def run_review(
    db_path: Path,
    *,
    limit: int = REVIEW_DEFAULT_LIMIT,
    confidence_threshold: float = REVIEW_CONFIDENCE_THRESHOLD,
    set_label: tuple[str, str] | None = None,
    expected_path: Path = DEFAULT_EXPECTED_LABELS,
    topics: str | None = None,
    classifier_name: str = MANUAL_CLASSIFIER_NAME,
    classifier_version: str = MANUAL_CLASSIFIER_VERSION,
    run_id: str | None = None,
    raw_local: bool = False,
    allow_external_db: bool = False,
) -> dict[str, object]:
    if limit <= 0:
        raise ValueError("--limit must be greater than 0")
    if confidence_threshold < 0 or confidence_threshold > 1:
        raise ValueError("--confidence-threshold must be between 0 and 1")

    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    validate_expected_labels_path(expected_path)
    manual_result: dict[str, object] | None = None

    db = Database(db_path)
    try:
        chat_aliases = db.chat_aliases()
        if set_label is not None:
            manual_result = _store_manual_label_correction(
                db,
                set_label=set_label,
                expected_path=expected_path,
                topics=topics,
                classifier_name=classifier_name,
                classifier_version=classifier_version,
                run_id=run_id or uuid4().hex,
                chat_aliases=chat_aliases,
                raw_local=raw_local,
            )

        low_confidence = db.review_label_candidates(
            confidence_threshold=confidence_threshold,
            limit=limit,
            include_preview=raw_local,
        )
        cluster_report = build_cluster_report(db.messages_for_clustering())
        solution_report = build_solution_report(db.messages_for_solutions())
    finally:
        db.close()

    cards = list(
        build_opportunity_cards(
            cluster_report.clusters,
            solution_report.records,
            limit=min(limit, MAX_OPPORTUNITY_CARDS),
        )
    )

    print("Review candidates")
    if manual_result is not None:
        print("")
        print("Manual correction stored:")
        print(
            "- "
            f"message_id={terminal_safe(manual_result['message_id'])} "
            f"previous={terminal_safe(manual_result['previous'])} "
            f"manual={terminal_safe(manual_result['manual'])} "
            f"topics={terminal_safe(manual_result['topics'])}"
        )
        print(
            "  "
            f"source=manual classifier={terminal_safe(classifier_name)} "
            f"{terminal_safe(classifier_version)} "
            f"run_id={terminal_safe(manual_result['run_id'])} "
            f"impact={terminal_safe(manual_result['impact'])}"
        )
        changes = manual_result["opportunity_changes"]
        if changes:
            print(
                "  "
                "opportunity_changes="
                f"{terminal_safe(';'.join(changes))}"
            )

    print("")
    print(f"Low-confidence/disputed labels: {len(low_confidence)}")
    if low_confidence:
        for row in low_confidence:
            message_id = _message_ref_display(
                str(row["chat_id"]),
                int(row["msg_id"]),
                chat_aliases,
                raw_local,
            )
            line = (
                "- "
                f"message_id={terminal_safe(message_id)} "
                f"category={terminal_safe(row['category'])} "
                f"confidence={float(row['confidence']):.2f} "
                f"topics={terminal_safe(row['topics'] or 'none')} "
                f"source={terminal_safe(row['source'])} "
                f"reason={terminal_safe(row['reason'])}"
            )
            if raw_local:
                line += f" preview={terminal_safe(row['preview'])}"
            print(line)
    else:
        print("- none")

    weak_clusters = [
        cluster
        for cluster in cluster_report.clusters
        if cluster.support_status == "weak_signal"
    ][:limit]
    print("")
    print(f"Weak-signal clusters: {len(weak_clusters)}")
    if weak_clusters:
        for cluster in weak_clusters:
            print(
                "- "
                f"cluster_id={terminal_safe(cluster.cluster_id)} "
                f"topic={terminal_safe(cluster.topic)} "
                f"unique_count={cluster.unique_count} "
                f"raw_count={cluster.raw_count} "
                f"weaker_evidence_count={cluster.weaker_evidence_count} "
                "evidence_message_ids="
                f"{terminal_safe(_cluster_evidence_ids(cluster, chat_aliases, raw_local))}"
            )
    else:
        print("- none")

    noise_cases = _review_noise_cases(cluster_report, limit=limit)
    print("")
    print(f"Disputed/noise cases: {len(noise_cases)}")
    if noise_cases:
        for item in noise_cases:
            print(
                "- "
                f"message_id={terminal_safe(_message_display_id(item['item'], chat_aliases, raw_local))} "
                f"category={terminal_safe(item['item'].category)} "
                f"problem_marker={terminal_safe(item['problem_marker'])} "
                f"match={terminal_safe(item['item'].matched_synonym)} "
                f"reason={terminal_safe(item['item'].reason)}"
            )
    else:
        print("- none")

    review_cards = []
    for card in cards:
        reasons = _opportunity_review_reasons(card)
        if reasons:
            review_cards.append((card, reasons))
    review_cards = review_cards[:limit]
    print("")
    print(f"Opportunity cards needing review: {len(review_cards)}")
    if review_cards:
        for card, reasons in review_cards:
            print(
                "- "
                f"opportunity_id={terminal_safe(card.opportunity_id)} "
                f"cluster_id={terminal_safe(card.cluster_id)} "
                f"score={card.score.total} "
                f"reasons={terminal_safe(';'.join(reasons))}"
            )
            print(
                "  "
                f"evidence_message_ids={terminal_safe(_card_review_source_ids(card, chat_aliases, raw_local))}"
            )
    else:
        print("- none")

    return {
        "manual_correction": manual_result,
        "low_confidence": _safe_low_confidence_results(
            low_confidence,
            chat_aliases,
            raw_local,
        ),
        "weak_clusters": _safe_weak_cluster_results(
            weak_clusters,
            chat_aliases,
            raw_local,
        ),
        "noise_cases": _safe_noise_case_results(
            noise_cases,
            chat_aliases,
            raw_local,
        ),
        "review_cards": _safe_review_card_results(
            review_cards,
            chat_aliases,
            raw_local,
        ),
    }


def run_summary(
    db_path: Path,
    *,
    limit: int = 5,
    confidence_threshold: float = REVIEW_CONFIDENCE_THRESHOLD,
    allow_external_db: bool = False,
) -> dict[str, object]:
    if limit <= 0:
        raise ValueError("--limit must be greater than 0")
    if limit > MAX_OPPORTUNITY_CARDS:
        raise ValueError(f"--limit must be <= {MAX_OPPORTUNITY_CARDS}")
    if confidence_threshold < 0 or confidence_threshold > 1:
        raise ValueError("--confidence-threshold must be between 0 and 1")

    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    db = Database(db_path)
    try:
        db.conn.execute("BEGIN")
        stats = db.stats()
        active_run = db.latest_classifier_run()
        distribution = db.label_distribution()
        frequencies = db.deduplicated_label_frequencies(KEY_FREQUENCY_CATEGORIES)
        chat_aliases = db.chat_aliases()
        low_confidence_count = db.review_label_candidate_count(
            confidence_threshold=confidence_threshold,
        )
        low_confidence = db.review_label_candidates(
            confidence_threshold=confidence_threshold,
            limit=limit,
            include_preview=False,
        )
        cluster_report = build_cluster_report(db.messages_for_clustering())
        solution_report = build_solution_report(db.messages_for_solutions())
    finally:
        if db.conn.in_transaction:
            db.conn.rollback()
        db.close()

    clusters = list(cluster_report.clusters)
    solution_records = list(solution_report.records)
    solution_display = _solution_display_records(
        solution_records,
        chat_aliases,
        _solution_locator_aliases(solution_records),
        raw_local=False,
    )
    all_cards = list(
        build_opportunity_cards(
            cluster_report.clusters,
            solution_report.records,
            limit=MAX_OPPORTUNITY_CARDS,
        )
    )
    cards = all_cards[:limit]
    weak_clusters = [
        cluster
        for cluster in clusters
        if cluster.support_status == "weak_signal"
    ]
    noise_case_capacity = sum(len(cluster.rejected) for cluster in clusters) + sum(
        len(group.rejected) for group in cluster_report.orphan_noise
    )
    noise_cases = _review_noise_cases(
        cluster_report,
        limit=max(noise_case_capacity, 1),
    )
    all_review_cards = [
        (card, reasons)
        for card in all_cards
        for reasons in (_opportunity_review_reasons(card),)
        if reasons
    ]

    safe_clusters = _safe_cluster_summary_results(
        clusters[:limit],
        chat_aliases,
    )
    safe_solutions = _safe_solution_summary_results(
        list(solution_display[:limit]),
    )
    safe_opportunities = _safe_opportunity_summary_results(
        cards,
        chat_aliases,
    )
    safe_low_confidence = _safe_low_confidence_results(
        low_confidence,
        chat_aliases,
        raw_local=False,
    )
    safe_weak_clusters = _safe_weak_cluster_results(
        weak_clusters[:limit],
        chat_aliases,
        raw_local=False,
    )
    safe_noise_cases = _safe_noise_case_results(
        noise_cases[:limit],
        chat_aliases,
        raw_local=False,
    )
    safe_review_cards = _safe_review_card_results(
        all_review_cards[:limit],
        chat_aliases,
        raw_local=False,
    )
    quality_gaps = _summary_quality_gaps(
        stats=stats,
        low_confidence_count=low_confidence_count,
        weak_cluster_count=len(weak_clusters),
        noise_case_count=len(noise_cases),
        review_card_count=len(all_review_cards),
        supported_cluster_count=sum(
            1 for cluster in clusters if cluster.support_status == "supported"
        ),
        solution_count=len(solution_display),
        opportunity_count=len(all_cards),
    )

    print("Research run summary")
    print("")
    print("Counts:")
    print(f"- chats={stats['chats']}")
    print(f"- messages={stats['messages']}")
    print(f"- labels={stats['labels']}")
    print(f"- unclassified={stats['unclassified']}")

    print("")
    print("Active classifier:")
    if active_run is None:
        print("- none")
    else:
        print(
            "- "
            f"{terminal_safe(active_run['source'])}/"
            f"{terminal_safe(active_run['classifier_name'])} "
            f"{terminal_safe(active_run['classifier_version'])} "
            f"run={terminal_safe(active_run['run_id'])}"
        )

    print("")
    print("Category distribution:")
    if distribution:
        for row in distribution:
            print(f"- {terminal_safe(row['category'])}: {row['count']}")
    else:
        print("- none")

    print("")
    print("Deduplicated frequencies:")
    if frequencies:
        for row in frequencies:
            print(
                "- "
                f"{terminal_safe(row['category'])}: "
                f"raw={row['raw_count']} "
                f"unique={row['unique_count']} "
                f"duplicates={row['duplicate_count']} "
                f"weak_evidence={row['weaker_evidence_count']}"
            )
    else:
        print("- none")

    print("")
    print(f"Top clusters: {len(safe_clusters)} of {len(clusters)}")
    if safe_clusters:
        for item in safe_clusters:
            print(
                "- "
                f"cluster_id={item['cluster_id']} "
                f"status={item['support_status']} "
                f"topic={item['topic']} "
                f"unique={item['unique_count']} "
                f"raw={item['raw_count']} "
                f"weak_evidence={item['weaker_evidence_count']} "
                f"evidence_message_ids={item['evidence_message_ids']}"
            )
    else:
        print("- none")

    print("")
    print(f"Solutions: {len(safe_solutions)} of {len(solution_display)}")
    if safe_solutions:
        for item in safe_solutions:
            print(
                "- "
                f"solution_id={item['solution_id']} "
                f"subtype={item['primary_subtype']} "
                f"type={item['solution_type']} "
                f"trust={item['trust_level']} "
                f"payment={item['payment_status']} "
                f"locators={item['locators']} "
                f"source_message_ids={item['source_message_ids']}"
            )
    else:
        print("- none")

    print("")
    print(f"Opportunities: {len(safe_opportunities)} of {len(all_cards)}")
    if safe_opportunities:
        for item in safe_opportunities:
            print(
                "- "
                f"opportunity_id={item['opportunity_id']} "
                f"cluster_id={item['cluster_id']} "
                f"status={item['support_status']} "
                f"score={item['score']} "
                f"verdict={item['verdict']} "
                f"first_mvp={item['first_mvp']} "
                f"payment_reason={item['payment_reason']}"
            )
    else:
        print("- none")

    print("")
    print("Review candidates:")
    print(
        "- "
        f"low_confidence_or_disputed_labels={low_confidence_count} "
        f"showing={len(safe_low_confidence)}"
    )
    for item in safe_low_confidence:
        print(
            "  - "
            f"message_id={item['message_id']} "
            f"category={item['category']} "
            f"confidence={item['confidence']:.2f} "
            f"reason={item['reason']}"
        )
    print(
        "- "
        f"weak_signal_clusters={len(weak_clusters)} "
        f"showing={len(safe_weak_clusters)}"
    )
    print(
        "- "
        f"disputed_noise_cases={len(noise_cases)} "
        f"showing={len(safe_noise_cases)}"
    )
    print(
        "- "
        f"opportunity_cards_needing_review={len(all_review_cards)} "
        f"showing={len(safe_review_cards)}"
    )

    print("")
    print("Quality gaps:")
    if quality_gaps:
        for gap in quality_gaps:
            print(f"- {terminal_safe(gap)}")
    else:
        print("- none")

    return {
        "counts": {
            "chats": int(stats["chats"]),
            "messages": int(stats["messages"]),
            "labels": int(stats["labels"]),
            "unclassified": int(stats["unclassified"]),
        },
        "active_classifier": (
            None
            if active_run is None
            else {
                "source": terminal_safe(active_run["source"]),
                "classifier_name": terminal_safe(active_run["classifier_name"]),
                "classifier_version": terminal_safe(active_run["classifier_version"]),
                "run_id": terminal_safe(active_run["run_id"]),
            }
        ),
        "category_distribution": [
            {
                "category": terminal_safe(row["category"]),
                "count": int(row["count"]),
            }
            for row in distribution
        ],
        "deduplicated_frequencies": [
            {
                "category": terminal_safe(row["category"]),
                "raw_count": int(row["raw_count"]),
                "unique_count": int(row["unique_count"]),
                "duplicate_count": int(row["duplicate_count"]),
                "weaker_evidence_count": int(row["weaker_evidence_count"]),
            }
            for row in frequencies
        ],
        "top_clusters": safe_clusters,
        "solutions": safe_solutions,
        "opportunities": safe_opportunities,
        "review_candidates": {
            "low_confidence_or_disputed_labels": low_confidence_count,
            "low_confidence": safe_low_confidence,
            "weak_signal_clusters": len(weak_clusters),
            "weak_clusters": safe_weak_clusters,
            "disputed_noise_cases": len(noise_cases),
            "noise_cases": safe_noise_cases,
            "opportunity_cards_needing_review": len(all_review_cards),
            "review_cards": safe_review_cards,
        },
        "quality_gaps": quality_gaps,
    }


def run_evaluate(
    db_path: Path,
    expected_path: Path = DEFAULT_EXPECTED_LABELS,
    *,
    classifier_name: str = CLASSIFIER_NAME,
    classifier_version: str | None = CLASSIFIER_VERSION,
    run_id: str | None = None,
    allow_external_db: bool = False,
) -> dict[str, object]:
    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    validate_expected_labels_path(expected_path)
    expected = load_expected_labels(expected_path)
    db = Database(db_path)
    try:
        active_run = db.latest_classifier_run(
            classifier_name=classifier_name,
            classifier_version=classifier_version,
            run_id=run_id,
        )
        base_rows = db.labels_for_classifier(
            classifier_name=classifier_name,
            classifier_version=classifier_version,
            run_id=run_id,
        )
        actual_rows = db.effective_labels_for_classifier(
            classifier_name=classifier_name,
            classifier_version=classifier_version,
            run_id=run_id,
        )
    finally:
        db.close()

    if active_run is None:
        version = classifier_version if classifier_version is not None else "latest"
        selected_run = run_id if run_id is not None else "latest"
        raise ValueError(
            "No classifier labels found for "
            f"{classifier_name} {version} run {selected_run}"
        )

    base_actual = {
        (str(row["chat_id"]), int(row["msg_id"])): str(row["category"])
        for row in base_rows
    }
    actual = {
        (str(row["chat_id"]), int(row["msg_id"])): str(row["category"])
        for row in actual_rows
    }
    actual_sources = {
        (str(row["chat_id"]), int(row["msg_id"])): str(row["source"])
        for row in actual_rows
    }
    expected_categories = {
        key: value["category"]
        for key, value in expected.items()
    }
    errors = [
        {
            "msg_id": key[1],
            "expected": expected_category,
            "actual": actual.get(key, "missing"),
        }
        for key, expected_category in sorted(expected_categories.items())
        if actual.get(key) != expected_category
    ]
    base_errors = [
        {
            "msg_id": key[1],
            "expected": expected_category,
            "actual": base_actual.get(key, "missing"),
        }
        for key, expected_category in sorted(expected_categories.items())
        if base_actual.get(key) != expected_category
    ]
    fixed_errors = [
        {
            "msg_id": key[1],
            "expected": expected_category,
            "previous": base_actual.get(key, "missing"),
            "manual": actual.get(key, "missing"),
        }
        for key, expected_category in sorted(expected_categories.items())
        if base_actual.get(key) != expected_category
        and actual.get(key) == expected_category
    ]
    introduced_errors = [
        {
            "msg_id": key[1],
            "expected": expected_category,
            "previous": base_actual.get(key, "missing"),
            "manual": actual.get(key, "missing"),
        }
        for key, expected_category in sorted(expected_categories.items())
        if base_actual.get(key) == expected_category
        and actual.get(key) != expected_category
    ]
    manual_override_count = sum(
        1
        for key in expected_categories
        if actual_sources.get(key) == "manual"
    )

    precision = {}
    for category in KEY_EVALUATION_CATEGORIES:
        predicted_keys = [
            key
            for key, actual_category in actual.items()
            if key in expected_categories and actual_category == category
        ]
        true_positive = sum(
            1 for key in predicted_keys if expected_categories[key] == category
        )
        denominator = len(predicted_keys)
        precision[category] = {
            "true_positive": true_positive,
            "predicted": denominator,
            "value": true_positive / denominator if denominator else None,
        }

    correct = len(expected_categories) - len(errors)
    measured_precisions = [
        item["value"] for item in precision.values() if item["value"] is not None
    ]
    macro_precision = (
        sum(measured_precisions) / len(measured_precisions)
        if measured_precisions
        else None
    )

    run_label = (
        f"{active_run['classifier_name']} "
        f"{active_run['classifier_version']} "
        f"run {active_run['run_id']}"
    )

    print(f"Control sample: {terminal_safe(expected_path)}")
    print(f"Classifier run: {terminal_safe(run_label)}")
    print(
        "Effective labels: "
        f"base classifier plus latest manual overrides "
        f"({manual_override_count} in control sample)"
    )
    print("")
    print("Precision:")
    for category in KEY_EVALUATION_CATEGORIES:
        item = precision[category]
        if item["value"] is None:
            value = "n/a"
        else:
            value = f"{item['value']:.2f}"
        print(
            f"- {category}: {value} "
            f"({item['true_positive']}/{item['predicted']})"
        )

    macro_text = "n/a" if macro_precision is None else f"{macro_precision:.2f}"
    print("")
    print(
        "Summary: "
        f"{correct}/{len(expected_categories)} labels correct; "
        f"macro precision {macro_text}; "
        f"errors {len(errors)}"
    )
    print("")
    print("Errors:")
    if errors:
        for error in errors:
            print(
                "- "
                f"msg_id={error['msg_id']} "
                f"expected={terminal_safe(error['expected'])} "
                f"actual={terminal_safe(error['actual'])}"
            )
    else:
        print("- none")

    print("")
    print("Manual impact:")
    if fixed_errors:
        for error in fixed_errors:
            print(
                "- fixed "
                f"msg_id={error['msg_id']} "
                f"expected={terminal_safe(error['expected'])} "
                f"was={terminal_safe(error['previous'])}"
            )
    if introduced_errors:
        for error in introduced_errors:
            print(
                "- introduced "
                f"msg_id={error['msg_id']} "
                f"expected={terminal_safe(error['expected'])} "
                f"was={terminal_safe(error['previous'])} "
                f"now={terminal_safe(error['manual'])}"
            )
    if not fixed_errors and not introduced_errors:
        print("- none")

    return {
        "precision": precision,
        "correct": correct,
        "total": len(expected_categories),
        "macro_precision": macro_precision,
        "errors": errors,
        "base_errors": base_errors,
        "fixed_errors": fixed_errors,
        "introduced_errors": introduced_errors,
        "manual_override_count": manual_override_count,
    }


def _store_manual_label_correction(
    db: Database,
    *,
    set_label: tuple[str, str],
    expected_path: Path,
    topics: str | None,
    classifier_name: str,
    classifier_version: str,
    run_id: str,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> dict[str, object]:
    target, category = set_label
    if category not in MESSAGE_CATEGORIES:
        raise ValueError(
            "Manual category must be one of: "
            f"{', '.join(MESSAGE_CATEGORIES)}"
        )

    chat_id, msg_id = _resolve_message_target(db, target, chat_aliases)
    previous = db.effective_label_for_message(chat_id, msg_id)
    resolved_topics = _parse_review_topics(topics, previous)
    impact = _manual_correction_impact(
        db,
        chat_id=chat_id,
        msg_id=msg_id,
        new_category=category,
        new_topics=resolved_topics,
        previous=previous,
        expected_path=expected_path,
    )
    if impact.evaluate_introduced_error:
        raise ValueError(
            "Manual correction would introduce an evaluate error; not stored."
        )
    if not impact.allows_write:
        raise ValueError(
            "Manual correction has no positive evaluate/card impact; "
            "not stored. Review edits must fix an evaluate error or change "
            "an opportunity card field/score."
        )

    label = LabelRecord(
        chat_id=chat_id,
        msg_id=msg_id,
        category=category,
        topics=resolved_topics,
        confidence=1.0,
        source="manual",
        classifier_name=classifier_name,
        classifier_version=classifier_version,
        run_id=run_id,
    )
    db.upsert_message_labels([label])

    message_id = _message_ref_display(chat_id, msg_id, chat_aliases, raw_local)
    previous_category = str(previous["category"]) if previous is not None else "missing"
    previous_source = str(previous["source"]) if previous is not None else "none"
    return {
        "message_id": message_id,
        "previous": f"{previous_category}/{previous_source}",
        "manual": category,
        "topics": ",".join(resolved_topics) if resolved_topics else "none",
        "run_id": run_id,
        "impact": impact.summary,
        "opportunity_changes": impact.opportunity_changes,
    }


def _resolve_message_target(
    db: Database,
    target: str,
    chat_aliases: dict[str, str],
) -> tuple[str, int]:
    target = target.strip()
    alias_to_chat_id = {alias: chat_id for chat_id, alias in chat_aliases.items()}

    if ":" in target:
        chat_token, msg_token = target.rsplit(":", 1)
        msg_id = _parse_msg_id(msg_token)
        chat_id = alias_to_chat_id.get(chat_token, chat_token)
    else:
        msg_id = _parse_msg_id(target)
        chat_ids = db.chat_ids_for_msg_id(msg_id)
        if not chat_ids:
            raise ValueError(f"Message not found: {target}")
        if len(chat_ids) > 1:
            raise ValueError(
                "Bare msg_id is ambiguous across chats; use chat alias like chat1:"
                f"{msg_id}"
            )
        chat_id = chat_ids[0]

    if not db.message_exists(chat_id, msg_id):
        raise ValueError(f"Message not found: {target}")
    return chat_id, msg_id


def _parse_msg_id(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid message id: {value}") from exc


def _parse_review_topics(
    topics: str | None,
    previous: object,
) -> list[str]:
    if topics is None:
        if previous is None:
            return []
        return [
            topic
            for topic in str(previous["topics"]).split(",")
            if topic
        ]

    parsed = [
        item.strip()
        for item in topics.split(",")
        if item.strip()
    ]
    unknown_topics = sorted(set(parsed) - set(PAIN_TOPICS))
    if unknown_topics:
        raise ValueError(
            "Manual topics must use known taxonomy values; unknown: "
            f"{', '.join(unknown_topics)}"
        )
    return parsed


def _manual_correction_impact(
    db: Database,
    *,
    chat_id: str,
    msg_id: int,
    new_category: str,
    new_topics: list[str],
    previous: object,
    expected_path: Path,
) -> ManualCorrectionImpact:
    expected = _load_expected_labels_if_available(expected_path)
    expected_category = expected.get((chat_id, msg_id), {}).get("category")
    previous_category = str(previous["category"]) if previous is not None else "missing"
    evaluate_fixed_error = bool(
        expected_category
        and previous_category != expected_category
        and new_category == expected_category
    )
    evaluate_introduced_error = bool(
        expected_category
        and previous_category == expected_category
        and new_category != expected_category
    )

    before_cluster_messages = db.messages_for_clustering()
    before_solution_messages = db.messages_for_solutions()
    before_cards = _cards_from_messages(
        before_cluster_messages,
        before_solution_messages,
    )
    after_cards = _cards_from_messages(
        _replace_message_label(
            before_cluster_messages,
            chat_id=chat_id,
            msg_id=msg_id,
            category=new_category,
            topics=tuple(new_topics),
        ),
        _replace_message_label(
            before_solution_messages,
            chat_id=chat_id,
            msg_id=msg_id,
            category=new_category,
            topics=tuple(new_topics),
        ),
    )
    opportunity_changes = _opportunity_card_changes(before_cards, after_cards)

    return ManualCorrectionImpact(
        evaluate_fixed_error=evaluate_fixed_error,
        evaluate_introduced_error=evaluate_introduced_error,
        opportunity_changed=bool(opportunity_changes),
        opportunity_changes=opportunity_changes,
    )


def _load_expected_labels_if_available(
    expected_path: Path,
) -> dict[tuple[str, int], dict[str, str]]:
    validate_expected_labels_path(expected_path)
    if not expected_path.exists():
        return {}
    return load_expected_labels(expected_path)


def _cards_from_messages(
    cluster_messages: list[object],
    solution_messages: list[object],
) -> tuple[OpportunityCard, ...]:
    cluster_report = build_cluster_report(cluster_messages)
    solution_report = build_solution_report(solution_messages)
    return build_opportunity_cards(
        cluster_report.clusters,
        solution_report.records,
        limit=MAX_OPPORTUNITY_CARDS,
    )


def _replace_message_label(
    messages: list[object],
    *,
    chat_id: str,
    msg_id: int,
    category: str,
    topics: tuple[str, ...],
) -> list[object]:
    replaced = []
    for message in messages:
        if message.chat_id == chat_id and message.msg_id == msg_id:
            replaced.append(replace(message, category=category, topics=topics))
        else:
            replaced.append(message)
    return replaced


def _opportunity_card_changes(
    before_cards: tuple[OpportunityCard, ...],
    after_cards: tuple[OpportunityCard, ...],
) -> tuple[str, ...]:
    before = _opportunity_snapshots(before_cards)
    after = _opportunity_snapshots(after_cards)
    changes = []
    for cluster_id in sorted(set(before) | set(after)):
        if cluster_id not in before:
            changes.append(f"{cluster_id}:added")
            continue
        if cluster_id not in after:
            changes.append(f"{cluster_id}:removed")
            continue
        changed_fields = [
            field
            for field, value in before[cluster_id].items()
            if after[cluster_id][field] != value
        ]
        if changed_fields:
            changes.append(f"{cluster_id}:{','.join(changed_fields)}")
    return tuple(changes)


def _opportunity_snapshots(
    cards: tuple[OpportunityCard, ...],
) -> dict[str, dict[str, object]]:
    return {
        card.cluster_id: {
            "support_status": card.support_status,
            "problem": card.problem,
            "audience": card.audience,
            "frequency": card.frequency,
            "current_workaround": card.current_workaround,
            "ready_solutions": card.ready_solutions,
            "first_mvp": card.first_mvp,
            "payment_reason": card.payment_reason,
            "complexity": card.complexity,
            "risk": card.risk,
            "score_total": card.score.total,
            "score_breakdown": (
                card.score.frequency,
                card.score.urgency,
                card.score.willingness_to_pay,
                card.score.mvp_speed,
                card.score.repeatability,
                card.score.defensibility,
                card.score.data_access,
            ),
        }
        for card in cards
    }


def _review_noise_cases(
    cluster_report: object,
    *,
    limit: int,
) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for cluster in cluster_report.clusters:
        for item in cluster.rejected:
            key = (item.message_ref, cluster.problem_marker, item.reason)
            if key in seen:
                continue
            seen.add(key)
            cases.append(
                {
                    "item": item,
                    "problem_marker": cluster.problem_marker,
                }
            )
    for group in cluster_report.orphan_noise:
        for item in group.rejected:
            key = (item.message_ref, group.problem_marker, item.reason)
            if key in seen:
                continue
            seen.add(key)
            cases.append(
                {
                    "item": item,
                    "problem_marker": group.problem_marker,
                }
            )
    return cases[:limit]


def _safe_low_confidence_results(
    rows: list[object],
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> list[dict[str, object]]:
    results = []
    for row in rows:
        item = {
            "message_id": terminal_safe(
                _message_ref_display(
                    str(row["chat_id"]),
                    int(row["msg_id"]),
                    chat_aliases,
                    raw_local,
                )
            ),
            "category": terminal_safe(row["category"]),
            "confidence": float(row["confidence"]),
            "topics": terminal_safe(row["topics"] or "none"),
            "source": terminal_safe(row["source"]),
            "reason": terminal_safe(row["reason"]),
        }
        if raw_local:
            item["preview"] = terminal_safe(row["preview"] or "")
        results.append(item)
    return results


def _safe_weak_cluster_results(
    clusters: list[ClusterRecord],
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> list[dict[str, object]]:
    return [
        {
            "cluster_id": terminal_safe(cluster.cluster_id),
            "topic": terminal_safe(cluster.topic),
            "unique_count": cluster.unique_count,
            "raw_count": cluster.raw_count,
            "weaker_evidence_count": cluster.weaker_evidence_count,
            "evidence_message_ids": terminal_safe(
                _cluster_evidence_ids(cluster, chat_aliases, raw_local)
            ),
        }
        for cluster in clusters
    ]


def _safe_noise_case_results(
    cases: list[dict[str, object]],
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> list[dict[str, object]]:
    results = []
    for case in cases:
        item = case["item"]
        results.append(
            {
                "message_id": terminal_safe(
                    _message_display_id(item, chat_aliases, raw_local)
                ),
                "category": terminal_safe(item.category),
                "problem_marker": terminal_safe(case["problem_marker"]),
                "match": terminal_safe(item.matched_synonym),
                "reason": terminal_safe(item.reason),
            }
        )
    return results


def _safe_review_card_results(
    review_cards: list[tuple[OpportunityCard, tuple[str, ...]]],
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> list[dict[str, object]]:
    return [
        {
            "opportunity_id": terminal_safe(card.opportunity_id),
            "cluster_id": terminal_safe(card.cluster_id),
            "score": card.score.total,
            "reasons": terminal_safe(";".join(reasons)),
            "evidence_message_ids": terminal_safe(
                _card_review_source_ids(card, chat_aliases, raw_local)
            ),
        }
        for card, reasons in review_cards
    ]


def _safe_cluster_summary_results(
    clusters: list[ClusterRecord],
    chat_aliases: dict[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "cluster_id": terminal_safe(cluster.cluster_id),
            "support_status": terminal_safe(cluster.support_status),
            "category": terminal_safe(cluster.category),
            "topic": terminal_safe(cluster.topic),
            "problem_marker": terminal_safe(cluster.problem_marker),
            "raw_count": cluster.raw_count,
            "unique_count": cluster.unique_count,
            "duplicate_count": cluster.duplicate_count,
            "weaker_evidence_count": cluster.weaker_evidence_count,
            "evidence_message_ids": terminal_safe(
                _cluster_evidence_ids(cluster, chat_aliases, raw_local=False)
            ),
        }
        for cluster in clusters
    ]


def _safe_solution_summary_results(
    records: list[SolutionDisplayRecord],
) -> list[dict[str, object]]:
    return [
        {
            "solution_id": terminal_safe(record.solution_id),
            "primary_subtype": terminal_safe(record.primary_subtype),
            "solution_type": terminal_safe(record.solution_type),
            "trust_level": terminal_safe(record.trust_level),
            "payment_status": terminal_safe(record.payment_status),
            "locators": terminal_safe(record.locators),
            "source_message_ids": terminal_safe(record.source_message_ids),
        }
        for record in records
    ]


def _safe_opportunity_summary_results(
    cards: list[OpportunityCard],
    chat_aliases: dict[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "opportunity_id": terminal_safe(card.opportunity_id),
            "cluster_id": terminal_safe(card.cluster_id),
            "support_status": terminal_safe(card.support_status),
            "score": card.score.total,
            "verdict": terminal_safe(card.score.verdict),
            "first_mvp": terminal_safe(card.first_mvp),
            "payment_reason": terminal_safe(card.payment_reason),
            "evidence_message_ids": terminal_safe(
                _card_review_source_ids(card, chat_aliases, raw_local=False)
            ),
        }
        for card in cards
    ]


def _summary_quality_gaps(
    *,
    stats: dict[str, int],
    low_confidence_count: int,
    weak_cluster_count: int,
    noise_case_count: int,
    review_card_count: int,
    supported_cluster_count: int,
    solution_count: int,
    opportunity_count: int,
) -> list[str]:
    gaps = []
    if stats["unclassified"]:
        gaps.append(f"unclassified_messages={stats['unclassified']}")
    if low_confidence_count:
        gaps.append(f"review_label_candidates={low_confidence_count}")
    if weak_cluster_count:
        gaps.append(f"weak_signal_clusters={weak_cluster_count}")
    if noise_case_count:
        gaps.append(f"disputed_noise_cases={noise_case_count}")
    if review_card_count:
        gaps.append(f"opportunity_cards_need_review={review_card_count}")
    if stats["messages"] and supported_cluster_count == 0:
        gaps.append("no_supported_clusters")
    if stats["messages"] and solution_count == 0:
        gaps.append("no_solution_records")
    if stats["messages"] and opportunity_count == 0:
        gaps.append("no_opportunities")
    return gaps


def _opportunity_review_reasons(card: OpportunityCard) -> tuple[str, ...]:
    reasons = []
    unknown_fields = [
        field
        for field in (
            "audience",
            "current_workaround",
            "ready_solutions",
            "first_mvp",
            "payment_reason",
            "complexity",
            "risk",
        )
        if getattr(card, field) == "unknown"
    ]
    if unknown_fields:
        reasons.append(f"unknown_fields={','.join(unknown_fields)}")
    if card.support_status == "weak_signal":
        reasons.append("weak_signal")

    weaker_evidence_count = _frequency_count(card.frequency, "weaker_evidence_count")
    if weaker_evidence_count > 0:
        reasons.append(f"weak_evidence={weaker_evidence_count}")

    risk_text = card.risk.lower()
    if card.complexity == "high" or any(marker in risk_text for marker in HIGH_RISK_MARKERS):
        reasons.append(f"high_risk={card.risk}")
    return tuple(reasons)


def _frequency_count(frequency: str, name: str) -> int:
    match = re.search(rf"{re.escape(name)}=(\d+)", frequency)
    if not match:
        return 0
    return int(match.group(1))


def _card_review_source_ids(
    card: OpportunityCard,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    source_ids = []
    seen = set()
    for item in card.evidence:
        for message_id in item.source_message_ids:
            if message_id in seen:
                continue
            seen.add(message_id)
            source_ids.append(message_id)
    return _opportunity_source_ids(tuple(source_ids), chat_aliases, raw_local)


def load_expected_labels(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    validate_expected_labels_path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected labels JSON root must be an object")

    labels = payload.get("labels")
    if not isinstance(labels, list):
        raise ValueError("Expected labels JSON must contain a 'labels' list")

    expected: dict[tuple[str, int], dict[str, str]] = {}
    for index, item in enumerate(labels):
        if not isinstance(item, dict):
            raise ValueError("Each expected label must be an object")
        missing = [
            key
            for key in ("chat_id", "msg_id", "category")
            if key not in item
        ]
        if missing:
            raise ValueError(
                "Expected label "
                f"at index {index} is missing required field(s): "
                f"{', '.join(missing)}"
            )

        chat_id = str(item["chat_id"])
        try:
            msg_id = int(item["msg_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Expected label at index {index} has invalid msg_id"
            ) from exc

        category = str(item["category"])
        if category not in MESSAGE_CATEGORIES:
            raise ValueError(
                f"Expected label at index {index} has invalid category: {category}"
            )
        expected[(chat_id, msg_id)] = {"category": category}
    return expected


def parse_latest_limit(value: str) -> int:
    try:
        latest = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--latest must be an integer") from exc

    try:
        return validate_latest_limit(latest)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def validate_latest_limit(latest: int) -> int:
    if latest < 0:
        raise ValueError("--latest must be >= 0")
    if latest > MAX_LATEST:
        raise ValueError(f"--latest must be <= {MAX_LATEST}")
    return latest


def validate_expected_labels_path(expected_path: Path) -> None:
    resolved_path = expected_path.resolve()
    name = expected_path.name.lower()
    if name == ".env" or name.startswith(".env."):
        raise ValueError(
            "Refusing to read expected labels from private or secret paths."
        )

    for private_dir in (Path("data/exports"), Path("data/db")):
        if resolved_path.is_relative_to(private_dir.resolve()):
            raise ValueError(
                "Refusing to read expected labels from private Telegram data paths."
            )

    if expected_path.suffix.lower() != ".json":
        raise ValueError("Refusing to read expected labels from a non-.json path.")


def validate_private_db_path(
    db_path: Path,
    *,
    allow_external_db: bool = False,
) -> None:
    if allow_external_db:
        return

    resolved_path = db_path.resolve()
    try:
        resolved_path.relative_to(DEFAULT_DB.parent.resolve())
        return
    except ValueError:
        pass

    try:
        resolved_path.relative_to(Path("tests").resolve())
        if db_path.name.startswith("_tmp") and db_path.suffix.lower() in PRIVATE_DB_SUFFIXES:
            return
    except ValueError:
        pass

    if db_path.suffix.lower() in PRIVATE_DB_SUFFIXES:
        raise ValueError(
            "Refusing to store private Telegram data outside data/db by default. "
            "Use data/db/, a tests/_tmp*.sqlite fixture DB, or pass "
            "--allow-external-db for explicit local-only external storage."
        )

    try:
        resolved_path.relative_to(DEFAULT_DB.parent.resolve())
        return
    except ValueError:
        pass

    raise ValueError(
        "Refusing to store private Telegram data in a DB path that may be tracked. "
        "Use data/db/, a tests/_tmp*.sqlite fixture DB, or pass "
        "--allow-external-db for explicit local-only external storage."
    )


def terminal_safe(value: object) -> str:
    text = str(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return CONTROL_CHARS_RE.sub("", text)


def _cluster_chat_aliases(
    clusters: list[ClusterRecord],
    orphan_noise: list[ClusterNoiseGroup],
) -> dict[str, str]:
    chat_ids = []
    for cluster in clusters:
        chat_ids.extend(item.chat_id for item in cluster.evidence)
        chat_ids.extend(item.chat_id for item in cluster.rejected)
    for group in orphan_noise:
        chat_ids.extend(item.chat_id for item in group.rejected)

    unique_chat_ids = sorted(set(chat_ids))
    return {
        chat_id: f"chat{index}"
        for index, chat_id in enumerate(unique_chat_ids, start=1)
    }


def _message_display_id(
    item: object,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    chat_id = str(getattr(item, "chat_id"))
    msg_id = int(getattr(item, "msg_id"))
    return _message_ref_display(chat_id, msg_id, chat_aliases, raw_local)


def _message_ref_display(
    chat_id: str,
    msg_id: int,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    if raw_local:
        return f"{chat_id}:{msg_id}"
    return f"{chat_aliases.get(chat_id, 'chat?')}:{msg_id}"


def _cluster_evidence_ids(
    cluster: ClusterRecord,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    return ",".join(
        _message_display_id(item, chat_aliases, raw_local)
        for item in cluster.evidence
    )


def _cluster_rejected_ids(
    cluster: ClusterRecord,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    return ",".join(
        _message_display_id(item, chat_aliases, raw_local)
        for item in cluster.rejected
    )


def _noise_group_rejected_ids(
    group: ClusterNoiseGroup,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    return ",".join(
        _message_display_id(item, chat_aliases, raw_local)
        for item in group.rejected
    )


def _solution_chat_aliases(records: list[SolutionRecord]) -> dict[str, str]:
    chat_ids = []
    for record in records:
        chat_ids.extend(mention.chat_id for mention in record.mentions)
    return {
        chat_id: f"chat{index}"
        for index, chat_id in enumerate(sorted(set(chat_ids)), start=1)
    }


def _opportunity_chat_aliases(cards: list[OpportunityCard]) -> dict[str, str]:
    chat_ids = []
    for card in cards:
        for item in card.evidence:
            for message_id in item.source_message_ids:
                chat_id, _msg_id = _split_message_ref(message_id)
                if chat_id:
                    chat_ids.append(chat_id)
    return {
        chat_id: f"chat{index}"
        for index, chat_id in enumerate(sorted(set(chat_ids)), start=1)
    }


def _opportunity_source_ids(
    source_message_ids: tuple[str, ...],
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    display_ids = []
    for message_id in source_message_ids:
        chat_id, msg_id = _split_message_ref(message_id)
        if raw_local or not chat_id:
            display_ids.append(message_id)
        else:
            display_ids.append(f"{chat_aliases.get(chat_id, 'chat?')}:{msg_id}")
    return ",".join(display_ids) if display_ids else "none"


def _split_message_ref(message_ref: str) -> tuple[str, str]:
    if ":" not in message_ref:
        return "", message_ref
    chat_id, msg_id = message_ref.rsplit(":", 1)
    return chat_id, msg_id


def _solution_locator_aliases(records: list[SolutionRecord]) -> dict[str, str]:
    counters = {"url": 0, "handle": 0}
    aliases: dict[str, str] = {}
    for record in records:
        for locator in record.locators:
            if locator in aliases:
                continue
            kind = "handle" if locator.startswith("@") else "url"
            counters[kind] += 1
            aliases[locator] = f"{kind}{counters[kind]}"
    return aliases


def _solution_identity(record: SolutionRecord, raw_local: bool) -> str:
    if raw_local:
        if record.name:
            return record.name
        return record.identity_key
    return record.solution_id


def _solution_locators(
    record: SolutionRecord,
    locator_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    if not record.locators:
        return "none"
    if raw_local:
        return ",".join(record.locators)
    return ",".join(locator_aliases[locator] for locator in record.locators)


def _solution_source_ids(
    record: SolutionRecord,
    chat_aliases: dict[str, str],
    raw_local: bool,
) -> str:
    return ",".join(
        _message_display_id(mention, chat_aliases, raw_local)
        for mention in record.mentions
    )


def _solution_display_records(
    records: list[SolutionRecord],
    chat_aliases: dict[str, str],
    locator_aliases: dict[str, str],
    raw_local: bool,
) -> tuple[SolutionDisplayRecord, ...]:
    return tuple(
        SolutionDisplayRecord(
            solution_id=record.solution_id,
            primary_subtype=record.primary_subtype,
            trust_level=record.trust_level,
            payment_status=record.payment_status,
            subtypes=_csv_or_none(record.subtypes),
            solution_type=record.solution_type,
            identity=_solution_identity(record, raw_local),
            locators=_solution_locators(record, locator_aliases, raw_local),
            promise=record.promise or "unknown",
            target_audience=_csv_or_none(record.target_audience),
            price=record.price or "unknown",
            ad_signals=_csv_or_none(record.ad_signals),
            trust_payment_signals=_csv_or_none(record.trust_payment_signals),
            source_message_ids=_solution_source_ids(record, chat_aliases, raw_local),
            mentions=tuple(
                SolutionDisplayMention(
                    message_id=_message_display_id(mention, chat_aliases, raw_local),
                    category=mention.category,
                    subtype=mention.subtype,
                    flags=_csv_or_none(mention.flags),
                )
                for mention in record.mentions
            ),
        )
        for record in records
    )


def _csv_or_none(values: tuple[str, ...]) -> str:
    return ",".join(values) if values else "none"


if __name__ == "__main__":
    main()
