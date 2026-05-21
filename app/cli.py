from __future__ import annotations

import argparse
import io
import json
import re
from contextlib import redirect_stdout
from dataclasses import dataclass, replace
from datetime import datetime
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
from app.web import render_html_report, write_static_site


DEFAULT_DB = Path("data/db/chatkb.sqlite")
DEFAULT_EXPECTED_LABELS = Path("tests/fixtures/telegram_expected_labels.json")
DEFAULT_REPORT = Path("data/reports/research-report.html")
DEFAULT_SITE_DIR = Path("data/reports/research-site")
DEFAULT_PROJECT_PROFILE = Path("data/reports/project-profile.json")
DEFAULT_DB_COMMAND_PATH = "<local-db-path>"
DEFAULT_SITE_COMMAND_PATH = "<local-site-dir>"
DEFAULT_PROFILE_COMMAND_PATH = "<local-profile-path>"
DEFAULT_PROJECT_NAME = "Market Pain Miner"
DEFAULT_PROJECT_SUMMARY = (
    "Локальная база знаний из Telegram-чата: боли, решения, инсайты "
    "и гипотезы для следующего продукта."
)
KEY_EVALUATION_CATEGORIES = ("pain", "question", "solution_ad", "tool_mention")
KEY_FREQUENCY_CATEGORIES = ("pain", "question", "solution_ad", "tool_mention")
PRIVATE_DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
PROJECT_PROFILE_LIST_FIELDS = (
    "target_segments",
    "focus_themes",
    "avoid_themes",
    "offer_types",
    "decision_criteria",
    "design_preferences",
    "next_questions",
)
PROJECT_PROFILE_TEMPLATE = {
    "project_name": "Market Pain Miner",
    "project_summary": "Локальный research bot для privacy-safe WB/Ozon-гипотез.",
    "user": "owner",
    "target_segments": [
        "WB/Ozon seller",
        "marketplace manager",
    ],
    "focus_themes": [
        "reviews",
        "penalties",
        "automation",
    ],
    "avoid_themes": [
        "raw personal data",
        "private chat attribution",
    ],
    "offer_types": [
        "audit report",
        "telegram alert",
        "local dashboard",
    ],
    "decision_criteria": [
        "repeated pain with evidence aliases",
        "clear manual workaround",
        "seller or manager can pay",
    ],
    "design_preferences": [
        "local-first",
        "privacy-safe",
        "evidence-backed",
    ],
    "next_questions": [
        "Which evidence aliases should be reviewed first?",
        "What can be validated without exposing raw chat data?",
    ],
}
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
MAX_REVIEW_COMMANDS = 7


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

    report_parser = subparsers.add_parser(
        "report",
        help="Generate a privacy-safe static HTML report",
    )
    report_parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT),
        help=f"Path to HTML report, default: {DEFAULT_REPORT}",
    )
    report_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=f"Max items per report section, 1-{MAX_OPPORTUNITY_CARDS}; default: 10",
    )
    report_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=REVIEW_CONFIDENCE_THRESHOLD,
        help=(
            "Labels at or below this confidence are counted as review candidates; "
            f"default: {REVIEW_CONFIDENCE_THRESHOLD}"
        ),
    )
    report_parser.add_argument(
        "--allow-external-report",
        action="store_true",
        help=(
            "Unsafe local-only: allow writing a generated report outside "
            "data/reports or tests/_tmp*.html"
        ),
    )

    site_parser = subparsers.add_parser(
        "site",
        help="Generate a privacy-safe multi-page local static site",
    )
    site_parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_SITE_DIR),
        help=f"Path to generated site folder, default: {DEFAULT_SITE_DIR}",
    )
    site_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help=f"Max items per site section, 1-{MAX_OPPORTUNITY_CARDS}; default: 20",
    )
    site_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=REVIEW_CONFIDENCE_THRESHOLD,
        help=(
            "Labels at or below this confidence are counted as review candidates; "
            f"default: {REVIEW_CONFIDENCE_THRESHOLD}"
        ),
    )
    site_parser.add_argument(
        "--project-name",
        default=DEFAULT_PROJECT_NAME,
        help="Project name shown in the generated site",
    )
    site_parser.add_argument(
        "--project-summary",
        default=DEFAULT_PROJECT_SUMMARY,
        help="Short project description shown in the generated site",
    )
    site_parser.add_argument(
        "--project-profile",
        default=None,
        help=(
            "Optional local JSON file with target_segments, focus_themes, "
            "offer_types and decision_criteria for a more personal for-you page"
        ),
    )
    site_parser.add_argument(
        "--db-command-path",
        default=DEFAULT_DB_COMMAND_PATH,
        help=(
            "Privacy-safe DB path string printed only in generated site "
            f"review commands, default: {DEFAULT_DB_COMMAND_PATH}"
        ),
    )
    site_parser.add_argument(
        "--site-command-path",
        default=DEFAULT_SITE_COMMAND_PATH,
        help=(
            "Privacy-safe site output path string printed only in generated "
            f"follow-up commands, default: {DEFAULT_SITE_COMMAND_PATH}"
        ),
    )
    site_parser.add_argument(
        "--profile-command-path",
        default=DEFAULT_PROFILE_COMMAND_PATH,
        help=(
            "Privacy-safe project profile path string printed only in generated "
            f"follow-up commands, default: {DEFAULT_PROFILE_COMMAND_PATH}"
        ),
    )
    site_parser.add_argument(
        "--allow-external-site",
        action="store_true",
        help=(
            "Unsafe local-only: allow writing a generated site outside "
            "data/reports or tests/_tmp*"
        ),
    )

    profile_template_parser = subparsers.add_parser(
        "profile-template",
        help="Create a privacy-safe JSON template for site --project-profile",
    )
    profile_template_parser.add_argument(
        "--output",
        default=str(DEFAULT_PROJECT_PROFILE),
        help=f"Path to JSON profile template, default: {DEFAULT_PROJECT_PROFILE}",
    )
    profile_template_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing local profile template file",
    )
    profile_template_parser.add_argument(
        "--allow-external-profile",
        action="store_true",
        help=(
            "Unsafe local-only: allow writing a project profile template outside "
            "data/reports or tests/_tmp*.json"
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
        elif args.command == "report":
            run_report(
                Path(args.db),
                Path(args.output),
                limit=args.limit,
                confidence_threshold=args.confidence_threshold,
                allow_external_db=args.allow_external_db,
                allow_external_report=args.allow_external_report,
            )
        elif args.command == "site":
            run_site(
                Path(args.db),
                Path(args.output_dir),
                limit=args.limit,
                confidence_threshold=args.confidence_threshold,
                project_name=args.project_name,
                project_summary=args.project_summary,
                project_profile_path=(
                    Path(args.project_profile) if args.project_profile else None
                ),
                db_command_path=args.db_command_path,
                site_command_path=args.site_command_path,
                profile_command_path=args.profile_command_path,
                allow_external_db=args.allow_external_db,
                allow_external_site=args.allow_external_site,
            )
        elif args.command == "profile-template":
            run_profile_template(
                Path(args.output),
                force=args.force,
                allow_external_profile=args.allow_external_profile,
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


def run_profile_template(
    output_path: Path = DEFAULT_PROJECT_PROFILE,
    *,
    force: bool = False,
    allow_external_profile: bool = False,
) -> dict[str, object]:
    validate_project_profile_template_path(
        output_path,
        allow_external_profile=allow_external_profile,
    )
    if output_path.exists() and not force:
        raise ValueError(
            "Project profile template already exists. "
            "Use --force to overwrite it intentionally."
        )

    payload = project_profile_template_payload()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Project profile template created")
    print(f"- path={terminal_safe(output_path)}")
    print(f"- next=python -m app.cli site --project-profile {terminal_safe(output_path)}")
    print("- privacy=fill this file locally; keep private notes in ignored paths")
    return {
        "path": terminal_safe(output_path),
        "payload": payload,
    }


def project_profile_template_payload() -> dict[str, object]:
    return json.loads(json.dumps(PROJECT_PROFILE_TEMPLATE, ensure_ascii=False))


def load_project_profile(profile_path: Path | None) -> dict[str, object]:
    if profile_path is None:
        return {}
    if not profile_path.exists():
        raise ValueError(f"Project profile not found: {profile_path}")
    if profile_path.suffix.lower() != ".json":
        raise ValueError("Project profile must be a JSON file")

    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Project profile JSON is invalid: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Project profile must contain a JSON object")

    profile: dict[str, object] = {}
    for key in ("project_name", "name", "project_summary", "summary", "user"):
        if key in payload:
            profile[key] = terminal_safe(payload[key])

    for key in PROJECT_PROFILE_LIST_FIELDS:
        profile[key] = _profile_text_list(payload.get(key))

    return profile


def _profile_text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("Project profile list fields must be strings or arrays")

    result = []
    seen = set()
    for item in values:
        text = terminal_safe(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text[:160])
    return result[:20]


def _project_profile_text(
    profile: dict[str, object],
    keys: tuple[str, ...],
    *,
    fallback: str,
    cli_default: str,
) -> str:
    if fallback != cli_default:
        return fallback
    for key in keys:
        value = str(profile.get(key, "")).strip()
        if value:
            return value
    return fallback


def run_report(
    db_path: Path,
    output_path: Path = DEFAULT_REPORT,
    *,
    limit: int = 10,
    confidence_threshold: float = REVIEW_CONFIDENCE_THRESHOLD,
    allow_external_db: bool = False,
    allow_external_report: bool = False,
) -> dict[str, object]:
    validate_report_path(output_path, allow_external_report=allow_external_report)
    captured = io.StringIO()
    with redirect_stdout(captured):
        payload = run_summary(
            db_path,
            limit=limit,
            confidence_threshold=confidence_threshold,
            allow_external_db=allow_external_db,
        )

    html = render_html_report(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print("HTML report generated")
    print(f"- path={terminal_safe(output_path)}")
    print(f"- messages={payload['counts']['messages']}")
    print(f"- opportunities={len(payload['opportunities'])}")
    print(f"- quality_gaps={len(payload['quality_gaps'])}")
    return {
        "path": terminal_safe(output_path),
        "payload": payload,
    }


def run_site(
    db_path: Path,
    output_dir: Path = DEFAULT_SITE_DIR,
    *,
    limit: int = 20,
    confidence_threshold: float = REVIEW_CONFIDENCE_THRESHOLD,
    project_name: str = DEFAULT_PROJECT_NAME,
    project_summary: str = DEFAULT_PROJECT_SUMMARY,
    project_profile_path: Path | None = None,
    db_command_path: str = DEFAULT_DB_COMMAND_PATH,
    site_command_path: str = DEFAULT_SITE_COMMAND_PATH,
    profile_command_path: str = DEFAULT_PROFILE_COMMAND_PATH,
    allow_external_db: bool = False,
    allow_external_site: bool = False,
) -> dict[str, object]:
    validate_site_dir_path(output_dir, allow_external_site=allow_external_site)
    project_profile = load_project_profile(project_profile_path)
    payload = build_site_payload(
        db_path,
        limit=limit,
        confidence_threshold=confidence_threshold,
        project_name=project_name,
        project_summary=project_summary,
        project_profile=project_profile,
        db_command_path=db_command_path,
        site_command_path=site_command_path,
        profile_command_path=profile_command_path,
        allow_external_db=allow_external_db,
    )
    write_static_site(payload, output_dir)

    print("Static site generated")
    print(f"- path={terminal_safe(output_dir)}")
    print(f"- open=index.html")
    print(f"- messages={payload['summary']['counts']['messages']}")
    print(f"- participants={len(payload['participants'])}")
    print(f"- tools={len(payload['tools'])}")
    print(f"- insights={len(payload['insights'])}")
    print(f"- niches={len(payload['niches'])}")
    if project_profile_path:
        print(f"- project_profile={terminal_safe(project_profile_path)}")
    print(
        "- serve="
        f"python -m http.server 8765 -d {terminal_safe(output_dir)}"
    )
    return {
        "path": terminal_safe(output_dir),
        "payload": payload,
    }


def build_site_payload(
    db_path: Path,
    *,
    limit: int,
    confidence_threshold: float,
    project_name: str,
    project_summary: str,
    project_profile: dict[str, object] | None = None,
    db_command_path: str = DEFAULT_DB_COMMAND_PATH,
    site_command_path: str = DEFAULT_SITE_COMMAND_PATH,
    profile_command_path: str = DEFAULT_PROFILE_COMMAND_PATH,
    allow_external_db: bool = False,
) -> dict[str, object]:
    if limit <= 0:
        raise ValueError("--limit must be greater than 0")
    if limit > MAX_OPPORTUNITY_CARDS:
        raise ValueError(f"--limit must be <= {MAX_OPPORTUNITY_CARDS}")

    captured = io.StringIO()
    with redirect_stdout(captured):
        summary = run_summary(
            db_path,
            limit=limit,
            confidence_threshold=confidence_threshold,
            allow_external_db=allow_external_db,
        )

    validate_private_db_path(db_path, allow_external_db=allow_external_db)
    db = Database(db_path)
    try:
        chat_aliases = db.chat_aliases()
        chat_meta = _site_chat_meta(db, chat_aliases)
        participants = _site_participants(db, chat_aliases, limit=limit)
        insights = _site_insights(db, chat_aliases, limit=limit)
        niches = _site_niches(db, chat_aliases, limit=limit)
    finally:
        db.close()

    project_profile = project_profile or {}
    project_name = _project_profile_text(
        project_profile,
        ("project_name", "name"),
        fallback=project_name,
        cli_default=DEFAULT_PROJECT_NAME,
    )
    project_summary = _project_profile_text(
        project_profile,
        ("project_summary", "summary"),
        fallback=project_summary,
        cli_default=DEFAULT_PROJECT_SUMMARY,
    )

    tools = _site_tools(summary)
    for_you = _site_for_you(
        project_name=project_name,
        project_summary=project_summary,
        project_profile=project_profile,
        summary=summary,
        participants=participants,
        niches=niches,
        insights=insights,
        command_hints=_site_command_hints(
            db_command_path=db_command_path,
            site_command_path=site_command_path,
            profile_command_path=profile_command_path,
        ),
    )

    return {
        "project": {
            "name": terminal_safe(project_name),
            "summary": terminal_safe(project_summary),
            "profile": project_profile,
        },
        "summary": summary,
        "participants": participants,
        "tools": tools,
        "insights": insights,
        "niches": niches,
        "for_you": for_you,
        "chat_meta": chat_meta,
    }


def _site_chat_meta(db: Database, chat_aliases: dict[str, str]) -> dict[str, object]:
    chat_rows = list(
        db.conn.execute(
            """
            SELECT chat_id, type, total_messages
            FROM chats
            ORDER BY chat_id ASC
            """
        )
    )
    msg_row = db.conn.execute(
        """
        SELECT
            COUNT(*) AS total_messages,
            MIN(msg_id) AS first_msg_id,
            MAX(msg_id) AS last_msg_id,
            MAX(date) AS last_date_iso
        FROM messages
        """
    ).fetchone()
    last_date, last_time = _format_site_datetime(
        str(msg_row["last_date_iso"] or "")
    )
    return {
        "chats": [
            {
                "chat_alias": terminal_safe(chat_aliases.get(str(row["chat_id"]), "chat?")),
                "type": terminal_safe(row["type"]),
                "declared_total_messages": int(row["total_messages"]),
            }
            for row in chat_rows
        ],
        "total_messages": int(msg_row["total_messages"] or 0),
        "first_msg_id": int(msg_row["first_msg_id"] or 0),
        "last_msg_id": int(msg_row["last_msg_id"] or 0),
        "last_date_iso": terminal_safe(msg_row["last_date_iso"] or ""),
        "last_date": last_date,
        "last_time": last_time,
        "privacy_mode": "aliases_only",
    }


def _site_participants(
    db: Database,
    chat_aliases: dict[str, str],
    *,
    limit: int,
) -> list[dict[str, object]]:
    rows = list(
        db.conn.execute(
            db.EFFECTIVE_LABELS_CTE
            + """
            SELECT
                m.from_id,
                COUNT(*) AS message_count,
                MIN(m.date) AS first_date,
                MAX(m.date) AS last_date,
                MIN(m.msg_id) AS first_msg_id,
                m.chat_id AS sample_chat_id,
                GROUP_CONCAT(DISTINCT COALESCE(el.category, 'unclassified'))
                    AS categories,
                GROUP_CONCAT(DISTINCT COALESCE(el.topics, ''))
                    AS topic_groups
            FROM messages AS m
            LEFT JOIN effective_labels AS el
              ON el.chat_id = m.chat_id
             AND el.msg_id = m.msg_id
            GROUP BY m.from_id
            ORDER BY message_count DESC, first_date ASC
            LIMIT ?
            """,
            (limit,),
        )
    )
    participants = []
    for index, row in enumerate(rows, start=1):
        categories = _csv_values_from_db(row["categories"])
        topics = _topic_values_from_db(row["topic_groups"])
        message_id = _message_ref_display(
            str(row["sample_chat_id"]),
            int(row["first_msg_id"]),
            chat_aliases,
            raw_local=False,
        )
        participants.append(
            {
                "id": f"person{index}",
                "name": f"participant{index}",
                "summary": (
                    "Активный участник выборки. Реальное имя скрыто "
                    "privacy-safe режимом."
                ),
                "message_count": int(row["message_count"]),
                "top_categories": ",".join(categories) if categories else "none",
                "topics": "|".join(topics) if topics else "none",
                "first_seen": terminal_safe(row["first_date"] or ""),
                "last_seen": terminal_safe(row["last_date"] or ""),
                "sample_message_id": terminal_safe(message_id),
            }
        )
    return participants


def _site_insights(
    db: Database,
    chat_aliases: dict[str, str],
    *,
    limit: int,
) -> list[dict[str, object]]:
    rows = list(
        db.conn.execute(
            db.EFFECTIVE_LABELS_CTE
            + """
            SELECT
                m.chat_id,
                m.msg_id,
                m.date,
                el.category,
                el.topics,
                el.confidence
            FROM messages AS m
            JOIN effective_labels AS el
              ON el.chat_id = m.chat_id
             AND el.msg_id = m.msg_id
            WHERE el.category IN ('case', 'insight', 'question')
            ORDER BY
                CASE el.category
                    WHEN 'case' THEN 1
                    WHEN 'insight' THEN 2
                    WHEN 'question' THEN 3
                    ELSE 9
                END,
                el.confidence DESC,
                m.date ASC
            LIMIT ?
            """,
            (limit,),
        )
    )
    return [
        {
            "id": f"insight{index}",
            "title": f"{terminal_safe(row['category'])}: {terminal_safe(row['topics'] or 'без темы')}",
            "category": terminal_safe(row["category"]),
            "summary": (
                "Сообщение требует ручного чтения: оно может быть вопросом, "
                "кейсом или инсайтом для будущей гипотезы."
            ),
            "tags": _topic_values_from_db(row["topics"]),
            "confidence": float(row["confidence"]),
            "message_id": terminal_safe(
                _message_ref_display(
                    str(row["chat_id"]),
                    int(row["msg_id"]),
                    chat_aliases,
                    raw_local=False,
                )
            ),
            "date": terminal_safe(row["date"]),
        }
        for index, row in enumerate(rows, start=1)
    ]


def _site_niches(
    db: Database,
    chat_aliases: dict[str, str],
    *,
    limit: int,
) -> list[dict[str, object]]:
    rows = list(
        db.conn.execute(
            db.EFFECTIVE_LABELS_CTE
            + """
            SELECT
                m.chat_id,
                m.msg_id,
                el.category,
                el.topics
            FROM messages AS m
            JOIN effective_labels AS el
              ON el.chat_id = m.chat_id
             AND el.msg_id = m.msg_id
            WHERE el.topics <> ''
            ORDER BY m.date ASC, m.msg_id ASC
            """
        )
    )
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        for topic in _topic_values_from_db(row["topics"]):
            item = grouped.setdefault(
                topic,
                {
                    "topic": topic,
                    "message_count": 0,
                    "categories": set(),
                    "evidence": [],
                },
            )
            item["message_count"] = int(item["message_count"]) + 1
            item["categories"].add(str(row["category"]))
            evidence = item["evidence"]
            if len(evidence) < 8:
                evidence.append(
                    _message_ref_display(
                        str(row["chat_id"]),
                        int(row["msg_id"]),
                        chat_aliases,
                        raw_local=False,
                    )
                )

    sorted_items = sorted(
        grouped.values(),
        key=lambda item: (-int(item["message_count"]), str(item["topic"])),
    )[:limit]
    return [
        {
            "id": f"topic{index}",
            "title": terminal_safe(item["topic"]),
            "summary": (
                "Тема часто встречалась в labels. Используй ее как вход "
                "для ручного просмотра кластеров и гипотез."
            ),
            "message_count": int(item["message_count"]),
            "categories": ",".join(sorted(item["categories"])),
            "evidence_message_ids": ",".join(item["evidence"]),
        }
        for index, item in enumerate(sorted_items, start=1)
    ]


def _site_tools(summary: dict[str, object]) -> list[dict[str, object]]:
    tools = []
    for index, item in enumerate(summary.get("solutions", []), start=1):
        tools.append(
            {
                "id": item["solution_id"],
                "name": item["solution_id"],
                "category": item["primary_subtype"],
                "solution_type": item["solution_type"],
                "payment_status": item["payment_status"],
                "trust_level": item["trust_level"],
                "description": (
                    "Упоминание решения или конкурента. Locator скрыт alias-ом: "
                    f"{item['locators']}."
                ),
                "rating": _tool_rating(str(item["trust_level"]), str(item["payment_status"])),
                "verdict": _tool_verdict(str(item["payment_status"])),
                "source_message_ids": item["source_message_ids"],
                "order": index,
            }
        )
    return tools


def _site_for_you(
    *,
    project_name: str,
    project_summary: str,
    project_profile: dict[str, object],
    summary: dict[str, object],
    participants: list[dict[str, object]],
    niches: list[dict[str, object]],
    insights: list[dict[str, object]],
    command_hints: dict[str, str],
) -> dict[str, object]:
    opportunities = list(summary.get("opportunities", []))
    quality_gaps = list(summary.get("quality_gaps", []))
    target_segments = _profile_values(project_profile, "target_segments")
    focus_themes = _profile_values(project_profile, "focus_themes")
    avoid_themes = _profile_values(project_profile, "avoid_themes")
    offer_types = _profile_values(project_profile, "offer_types")
    decision_criteria = _profile_values(project_profile, "decision_criteria")
    design_preferences = _profile_values(project_profile, "design_preferences")
    next_questions = _profile_values(project_profile, "next_questions")
    profile_analysis = _site_profile_analysis(
        focus_themes=focus_themes,
        avoid_themes=avoid_themes,
        opportunities=opportunities,
        niches=niches,
        insights=insights,
        next_questions=next_questions,
        quality_gaps=quality_gaps,
    )
    opportunity_state = profile_analysis["opportunity_state"]
    ordered_opportunities = _profile_ordered_opportunities(
        opportunities,
        opportunity_state,
        has_focus=bool(focus_themes),
    )

    now = []
    for index, item in enumerate(ordered_opportunities[:5], start=1):
        item_profile = opportunity_state.get(str(item.get("opportunity_id", "")), {})
        actions = [
            f"Открыть evidence IDs: {item['evidence_message_ids']}",
            f"Проверить MVP: {item['first_mvp']}",
            "Решить GO / PIVOT / STOP до разработки продукта.",
        ]
        matched_themes = list(item_profile.get("matched_themes", []))
        avoided_themes = list(item_profile.get("avoid_themes", []))
        if matched_themes:
            actions.append(
                "Profile match: сверить evidence с focus_themes "
                f"{_join_profile_values(matched_themes)}."
            )
        if avoided_themes:
            actions.append(
                "Avoid warning: тема попала в avoid_themes "
                f"{_join_profile_values(avoided_themes)}; evidence не удалять."
            )
        if focus_themes:
            actions.append(
                "Сверить гипотезу с фокус-темами: "
                f"{_join_profile_values(focus_themes)}."
            )
        if target_segments:
            actions.append(
                "Проверить на первом сегменте: "
                f"{_join_profile_values(target_segments)}."
            )
        if decision_criteria:
            actions.append(
                "Оценить по критериям владельца: "
                f"{_join_profile_values(decision_criteria)}."
            )
        profile_reason = _profile_now_reason(item_profile)
        why = (
            f"Score={item['score']}, verdict={item['verdict']}, "
            f"payment_reason={item['payment_reason']}."
        )
        if profile_reason:
            why = f"{why} {profile_reason}"
        now.append(
            {
                "title": f"Проверить гипотезу {item['opportunity_id']}",
                "type": "opportunity",
                "priority": _profile_now_priority(
                    index,
                    item_profile,
                    has_focus=bool(focus_themes),
                ),
                "actions": actions,
                "why": why,
            }
        )
    if not now:
        now.append(
            {
                "title": "Усилить выборку перед выбором продукта",
                "type": "research",
                "priority": "P0",
                "actions": [
                    "Открыть раздел Инсайты и ручную проверку.",
                    "Добавить manual labels для спорных сообщений.",
                    _fallback_focus_action(focus_themes, target_segments),
                    "Перегенерировать сайт после review.",
                ],
                "why": "В summary пока нет сильных opportunity cards.",
            }
        )

    people_to_contact = [
        {
            "name": item["name"],
            "project": item.get("topics", "unknown"),
            "why": (
                "Этот participant alias активен в выборке. Проверь его "
                f"сообщения начиная с {item['sample_message_id']}."
            ),
            "ask": "Какая повторяющаяся боль или готовое решение стоит за его сообщениями?",
        }
        for item in participants[:8]
    ]

    to_apply = [
        {
            "from": f"Тема {item['title']}",
            "what": item["summary"],
            "applicability": _profile_applicability(
                project_name,
                target_segments,
                offer_types,
            ),
            "rating": 4 if int(item["message_count"]) >= 3 else 3,
        }
        for item in niches[:8]
    ]

    open_issues = [
        {
            "issue": gap,
            "your_status": "Нужно проверить качество анализа до продуктового решения.",
            "ideas_from_chat": [
                "Открыть review candidates.",
                "Сверить evidence IDs в разделах Кластеры/Инсайты.",
            ],
        }
        for gap in quality_gaps[:5]
    ]
    open_issues.extend(
        {
            "issue": question,
            "your_status": "Вопрос из project profile, нужен ответ после просмотра evidence.",
            "ideas_from_chat": [
                "Проверить разделы Для тебя и Темы.",
                "Сравнить с focus_themes и decision_criteria.",
            ],
        }
        for question in next_questions[:5]
    )

    project_fit = [
        _project_fit_block(
            "Целевая аудитория",
            target_segments,
            "Кому должен быть полезен следующий MVP.",
        ),
        _project_fit_block(
            "Фокус-темы",
            focus_themes,
            "Какие темы считать приоритетными при чтении evidence.",
        ),
        _project_fit_block(
            "Форматы продукта",
            offer_types,
            "Во что можно упаковать найденную возможность.",
        ),
        _project_fit_block(
            "Критерии решения",
            decision_criteria,
            "Как принять GO / PIVOT / STOP после ручной проверки.",
        ),
    ]
    if avoid_themes:
        project_fit.append(
            _project_fit_block(
                "Не в фокусе",
                avoid_themes,
                "Темы, которые лучше не превращать в MVP без отдельного решения.",
            )
        )

    return {
        "user": terminal_safe(project_profile.get("user", "owner")),
        "project": f"{terminal_safe(project_name)} — {terminal_safe(project_summary)}",
        "summary": (
            "Персональная подборка построена автоматически из privacy-safe "
            "summary, opportunities, participants aliases, topic aggregates "
            "и локального project profile."
        ),
        "project_profile": {
            "target_segments": target_segments,
            "focus_themes": focus_themes,
            "avoid_themes": avoid_themes,
            "offer_types": offer_types,
            "decision_criteria": decision_criteria,
            "design_preferences": design_preferences,
            "next_questions": next_questions,
        },
        "project_fit": project_fit,
        "profile_matches": profile_analysis["profile_matches"],
        "recommended_next_review": profile_analysis["recommended_next_review"],
        "review_commands": _review_commands_for_matches(
            matches=profile_analysis["profile_matches"],
            focus_themes=focus_themes,
            command_hints=command_hints,
        ),
        "profile_warnings": profile_analysis["profile_warnings"],
        "now": now,
        "people_to_contact": people_to_contact,
        "to_apply": to_apply,
        "open_issues_to_solve": open_issues,
        "principles_to_remember": _profile_principles(
            decision_criteria,
            design_preferences,
        ),
        "deferred": [
            {
                "title": "Полный dashboard",
                "rationale": "Сначала проверить полезность static site.",
                "when": "Когда HTML-разделы начнут регулярно использоваться в пилотах.",
            }
        ],
    }


def _site_profile_analysis(
    *,
    focus_themes: list[str],
    avoid_themes: list[str],
    opportunities: list[dict[str, object]],
    niches: list[dict[str, object]],
    insights: list[dict[str, object]],
    next_questions: list[str],
    quality_gaps: list[object],
) -> dict[str, object]:
    candidates = _profile_candidates(
        opportunities=opportunities,
        niches=niches,
        insights=insights,
    )
    matches = []
    avoid_candidates = []
    opportunity_state: dict[str, dict[str, object]] = {}

    for candidate in candidates:
        matched_themes = _matched_profile_themes(
            focus_themes,
            candidate["terms"],
        )
        avoided_themes = _matched_profile_themes(
            avoid_themes,
            candidate["terms"],
        )
        if candidate["type"] == "opportunity":
            opportunity_state[str(candidate["id"])] = {
                "matched_themes": matched_themes,
                "avoid_themes": avoided_themes,
            }
        if avoided_themes:
            avoid_candidates.append({**candidate, "avoid_themes": avoided_themes})
        if not matched_themes:
            continue
        match = {
            "type": candidate["type"],
            "id": candidate["id"],
            "title": candidate["title"],
            "matched_themes": matched_themes,
            "matched_topic": _profile_match_topic(
                matched_themes,
                candidate.get("source_topics", []),
            ),
            "avoid_themes": avoided_themes,
            "priority": _profile_match_priority(
                str(candidate["type"]),
                avoided_themes,
            ),
            "reason": _profile_match_reason(
                str(candidate["type"]),
                matched_themes,
                avoided_themes,
            ),
            "evidence_aliases": candidate["evidence_aliases"],
            "source_category": candidate.get("source_category", ""),
            "source_topics": candidate.get("source_topics", []),
            "_sort_group": candidate["sort_group"],
            "_sort_order": candidate["sort_order"],
        }
        matches.append(match)

    matches.sort(key=_profile_match_sort_key)
    public_matches = [
        {key: value for key, value in match.items() if not key.startswith("_")}
        for match in matches
    ]
    warnings = _profile_warnings(
        focus_themes=focus_themes,
        matches=public_matches,
        avoid_candidates=avoid_candidates,
    )
    return {
        "profile_matches": public_matches,
        "recommended_next_review": _recommended_next_review(
            matches=public_matches,
            warnings=warnings,
            focus_themes=focus_themes,
            next_questions=next_questions,
            opportunities=opportunities,
            quality_gaps=quality_gaps,
        ),
        "profile_warnings": warnings,
        "opportunity_state": opportunity_state,
    }


def _profile_candidates(
    *,
    opportunities: list[dict[str, object]],
    niches: list[dict[str, object]],
    insights: list[dict[str, object]],
) -> list[dict[str, object]]:
    candidates = []
    for index, item in enumerate(opportunities, start=1):
        cluster_topic = _topic_from_cluster_id(str(item.get("cluster_id", "")))
        cluster_category = _category_from_cluster_id(str(item.get("cluster_id", "")))
        candidates.append(
            {
                "type": "opportunity",
                "id": terminal_safe(item.get("opportunity_id", f"opportunity{index}")),
                "title": terminal_safe(
                    f"Гипотеза {item.get('opportunity_id', f'opportunity{index}')}"
                ),
                "terms": _profile_match_terms(
                    item.get("opportunity_id", ""),
                    item.get("cluster_id", ""),
                    cluster_topic,
                    item.get("support_status", ""),
                    item.get("verdict", ""),
                    item.get("first_mvp", ""),
                    item.get("payment_reason", ""),
                ),
                "evidence_aliases": _evidence_aliases(
                    item.get("evidence_message_ids", "")
                ),
                "source_category": cluster_category or "pain",
                "source_topics": [cluster_topic] if cluster_topic else [],
                "sort_group": 0,
                "sort_order": index,
            }
        )
    for index, item in enumerate(niches, start=1):
        title = terminal_safe(item.get("title", f"topic{index}"))
        source_topics = [title] if title in PAIN_TOPICS else []
        candidates.append(
            {
                "type": "theme",
                "id": terminal_safe(item.get("id", f"topic{index}")),
                "title": f"Тема {title}",
                "terms": _profile_match_terms(
                    title,
                    item.get("categories", ""),
                ),
                "evidence_aliases": _evidence_aliases(
                    item.get("evidence_message_ids", "")
                ),
                "source_category": "pain" if source_topics else "insight",
                "source_topics": source_topics,
                "sort_group": 1,
                "sort_order": index,
            }
        )
    for index, item in enumerate(insights, start=1):
        source_category = terminal_safe(item.get("category", "insight"))
        candidates.append(
            {
                "type": "insight",
                "id": terminal_safe(item.get("id", f"insight{index}")),
                "title": terminal_safe(item.get("title", f"insight{index}")),
                "terms": _profile_match_terms(
                    item.get("category", ""),
                    item.get("title", ""),
                    item.get("tags", []),
                ),
                "evidence_aliases": _evidence_aliases(item.get("message_id", "")),
                "source_category": source_category,
                "source_topics": [
                    topic for topic in item.get("tags", []) if topic in PAIN_TOPICS
                ],
                "sort_group": 2,
                "sort_order": index,
            }
        )
    return candidates


def _profile_match_terms(*values: object) -> set[str]:
    terms: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple, set)):
            terms.update(_profile_match_terms(*value))
            continue
        text = terminal_safe(value).strip().lower()
        if not text or text == "none":
            continue
        terms.add(text)
        terms.add(text.replace(" ", "_"))
        terms.add(text.replace("_", " "))
        for token in re.split(r"[^0-9a-zа-яё]+", text):
            if token and token != "none":
                terms.add(token)
    return terms


def _matched_profile_themes(themes: list[str], terms: set[str]) -> list[str]:
    matched = []
    for theme in themes:
        text = terminal_safe(theme).strip().lower()
        if not text:
            continue
        variants = {
            text,
            text.replace(" ", "_"),
            text.replace("_", " "),
        }
        if variants & terms:
            matched.append(terminal_safe(theme))
    return matched


def _profile_match_topic(
    matched_themes: list[str],
    source_topics: object,
) -> str:
    matched_topics = set(_controlled_review_topics(matched_themes))
    for topic in _controlled_review_topics(source_topics):
        if not matched_topics or topic in matched_topics:
            return topic
    for topic in _controlled_review_topics(matched_themes):
        return topic
    return ""


def _topic_from_cluster_id(cluster_id: str) -> str:
    parts = cluster_id.split(":")
    if len(parts) >= 3:
        return parts[1]
    return ""


def _category_from_cluster_id(cluster_id: str) -> str:
    parts = cluster_id.split(":")
    if len(parts) >= 3 and parts[0] in MESSAGE_CATEGORIES:
        return parts[0]
    return ""


def _evidence_aliases(value: object) -> list[str]:
    aliases = []
    for item in str(value or "").split(","):
        alias = terminal_safe(item).strip()
        if alias and alias != "none":
            aliases.append(alias)
    return aliases


def _profile_match_priority(source_type: str, avoided_themes: list[str]) -> str:
    if avoided_themes:
        return "P2"
    if source_type == "opportunity":
        return "P0"
    return "P1"


def _profile_match_reason(
    source_type: str,
    matched_themes: list[str],
    avoided_themes: list[str],
) -> str:
    source_label = {
        "opportunity": "opportunity",
        "theme": "topic aggregate",
        "insight": "insight",
    }.get(source_type, source_type)
    reason = (
        f"{source_label} совпал с focus_themes: "
        f"{_join_profile_values(matched_themes)}."
    )
    if avoided_themes:
        reason += (
            " Совпадение также попало в avoid_themes, поэтому priority снижен, "
            "а evidence оставлен для ручной проверки."
        )
    return reason


def _profile_match_sort_key(match: dict[str, object]) -> tuple[int, int, int, str]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}.get(str(match["priority"]), 9)
    return (
        priority_rank,
        int(match["_sort_group"]),
        int(match["_sort_order"]),
        str(match["id"]),
    )


def _profile_warnings(
    *,
    focus_themes: list[str],
    matches: list[dict[str, object]],
    avoid_candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    warnings = []
    if not focus_themes:
        warnings.append(
            _profile_warning(
                "focus_themes_empty",
                "focus_themes пустые; профиль показан, но рекомендации не ранжируются по фокусу.",
                priority="P1",
            )
        )

    if avoid_candidates:
        warnings.append(
            _profile_warning(
                "avoid_themes_detected",
                "Найдены темы из avoid_themes; evidence не скрыт, но такие элементы требуют осторожного review.",
                priority="P2",
                themes=_unique_profile_values(
                    theme
                    for candidate in avoid_candidates
                    for theme in candidate.get("avoid_themes", [])
                ),
                evidence_aliases=_merge_evidence_aliases(avoid_candidates),
            )
        )

    if focus_themes and not matches:
        warnings.append(
            _profile_warning(
                "no_matched_evidence",
                "Ни одна topic/opportunity/insight не совпала с focus_themes.",
                priority="P1",
                themes=focus_themes,
            )
        )

    if avoid_candidates and (
        not matches or all(match.get("avoid_themes") for match in matches)
    ):
        warnings.append(
            _profile_warning(
                "all_matches_only_in_avoid_themes",
                "Все найденные profile-сигналы относятся только к avoid_themes или пересекаются с ними.",
                priority="P2",
                themes=_unique_profile_values(
                    theme
                    for candidate in avoid_candidates
                    for theme in candidate.get("avoid_themes", [])
                ),
                evidence_aliases=_merge_evidence_aliases(avoid_candidates),
            )
        )
    return warnings


def _profile_warning(
    code: str,
    message: str,
    *,
    priority: str,
    themes: list[str] | None = None,
    evidence_aliases: list[str] | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "priority": priority,
        "themes": themes or [],
        "evidence_aliases": evidence_aliases or [],
    }


def _recommended_next_review(
    *,
    matches: list[dict[str, object]],
    warnings: list[dict[str, object]],
    focus_themes: list[str],
    next_questions: list[str],
    opportunities: list[dict[str, object]],
    quality_gaps: list[object],
) -> list[dict[str, object]]:
    actions = []
    for match in matches[:5]:
        actions.append(
            {
                "title": f"Проверить {match['title']}",
                "priority": match.get("priority", "P1"),
                "action": _review_action_for_match(str(match.get("type", ""))),
                "reason": match.get("reason", ""),
                "evidence_aliases": match.get("evidence_aliases", []),
            }
        )

    for question in next_questions[:2]:
        actions.append(
            {
                "title": "Ответить на вопрос из project profile",
                "priority": "P1",
                "action": terminal_safe(question),
                "reason": "Вопрос добавлен владельцем проекта и должен быть закрыт после просмотра evidence.",
                "evidence_aliases": [],
            }
        )

    if not focus_themes:
        actions.append(
            {
                "title": "Заполнить focus_themes",
                "priority": "P0",
                "action": "Добавить 1-5 controlled marketplace themes в локальный project profile.",
                "reason": "Без focus_themes сайт не может персонально ранжировать рекомендации.",
                "evidence_aliases": [],
            }
        )

    if any(warning.get("code") == "avoid_themes_detected" for warning in warnings):
        warning = next(
            item for item in warnings if item.get("code") == "avoid_themes_detected"
        )
        actions.append(
            {
                "title": "Разобрать avoid_themes",
                "priority": "P2",
                "action": "Проверить, почему эти evidence aliases попали в avoid_themes, и не превращать их в MVP без отдельного решения.",
                "reason": warning.get("message", ""),
                "evidence_aliases": warning.get("evidence_aliases", []),
            }
        )

    for item in opportunities[:2]:
        actions.append(
            {
                "title": f"Открыть evidence гипотезы {item.get('opportunity_id', 'unknown')}",
                "priority": "P1",
                "action": "Сверить aliases с кластерами и решить GO / PIVOT / STOP.",
                "reason": (
                    f"Score={terminal_safe(item.get('score', 'unknown'))}, "
                    f"verdict={terminal_safe(item.get('verdict', 'unknown'))}."
                ),
                "evidence_aliases": _evidence_aliases(
                    item.get("evidence_message_ids", "")
                ),
            }
        )

    for gap in quality_gaps[:2]:
        actions.append(
            {
                "title": "Закрыть quality gap",
                "priority": "P1",
                "action": terminal_safe(gap),
                "reason": "Качество анализа влияет на продуктовые выводы.",
                "evidence_aliases": [],
            }
        )

    fallbacks = [
        {
            "title": "Проверить top topics",
            "priority": "P1",
            "action": "Открыть раздел Темы и сверить первые evidence aliases.",
            "reason": "Топики дают быстрый вход в повторяемые паттерны.",
            "evidence_aliases": [],
        },
        {
            "title": "Проверить review candidates",
            "priority": "P1",
            "action": "Запустить review и уточнить спорные labels перед продуктовым решением.",
            "reason": "Manual review снижает риск ложной гипотезы.",
            "evidence_aliases": [],
        },
        {
            "title": "Перегенерировать сайт после review",
            "priority": "P2",
            "action": "После ручных правок labels снова выполнить site.",
            "reason": "Рекомендации должны строиться из актуальных labels.",
            "evidence_aliases": [],
        },
    ]
    seen_titles = {str(item["title"]) for item in actions}
    for fallback in fallbacks:
        if len(actions) >= 3:
            break
        if fallback["title"] in seen_titles:
            continue
        actions.append(fallback)
        seen_titles.add(fallback["title"])
    return actions[:7]


def _review_action_for_match(source_type: str) -> str:
    if source_type == "opportunity":
        return "Открыть aliases гипотезы, проверить MVP/payment_reason и принять GO / PIVOT / STOP."
    if source_type == "theme":
        return "Открыть aliases темы и проверить, есть ли повторяемая боль или готовое решение."
    if source_type == "insight":
        return "Открыть alias инсайта и вручную решить, превращается ли он в проверяемую гипотезу."
    return "Открыть aliases и проверить вывод вручную."


def _site_command_hints(
    *,
    db_command_path: str,
    site_command_path: str,
    profile_command_path: str,
) -> dict[str, str]:
    return {
        "db": _command_hint(db_command_path, DEFAULT_DB_COMMAND_PATH),
        "site": _command_hint(site_command_path, DEFAULT_SITE_COMMAND_PATH),
        "profile": _command_hint(
            profile_command_path,
            DEFAULT_PROFILE_COMMAND_PATH,
        ),
    }


def _command_hint(value: object, default: str) -> str:
    text = terminal_safe(value).strip()
    return text or default


def _review_commands_for_matches(
    *,
    matches: list[dict[str, object]],
    focus_themes: list[str],
    command_hints: dict[str, str],
) -> list[dict[str, object]]:
    commands = []
    seen: set[tuple[str, str, str]] = set()
    db_path = _command_hint(command_hints.get("db", ""), DEFAULT_DB_COMMAND_PATH)
    site_path = _command_hint(
        command_hints.get("site", ""),
        DEFAULT_SITE_COMMAND_PATH,
    )
    profile_path = _command_hint(
        command_hints.get("profile", ""),
        DEFAULT_PROFILE_COMMAND_PATH,
    )
    followup_command = (
        "python -m app.cli "
        f"--db {db_path} "
        "site "
        f"--output-dir {site_path} "
        f"--project-profile {profile_path}"
    )

    for match in matches:
        category = _suggested_review_category(match)
        topics = _suggested_review_topics(
            focus_themes=focus_themes,
            match=match,
        )
        topic_arg = f" --topics {','.join(topics)}" if topics else ""
        for evidence_alias in match.get("evidence_aliases", []):
            alias = terminal_safe(evidence_alias).strip()
            if not alias:
                continue
            dedupe_key = (alias, category, ",".join(topics))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            command = (
                "python -m app.cli "
                f"--db {db_path} "
                "review "
                f"--set-label {alias} {category}"
                f"{topic_arg}"
            )
            commands.append(
                {
                    "title": terminal_safe(f"Разметить {alias}: {match.get('title', '')}"),
                    "reason": terminal_safe(match.get("reason", "")),
                    "evidence_alias": alias,
                    "suggested_category": category,
                    "suggested_topics": topics,
                    "command": terminal_safe(command),
                    "followup_command": terminal_safe(followup_command),
                    "priority": terminal_safe(match.get("priority", "P1")),
                }
            )
            if len(commands) >= MAX_REVIEW_COMMANDS:
                return commands
    return commands


def _suggested_review_category(match: dict[str, object]) -> str:
    source_type = str(match.get("type", ""))
    if source_type in {"opportunity", "theme"}:
        return "pain"

    source_category = terminal_safe(match.get("source_category", "")).strip()
    if source_category == "question":
        return "question"
    if source_category in {"insight", "case"}:
        return "insight"
    if source_category in MESSAGE_CATEGORIES:
        return source_category
    return "insight"


def _suggested_review_topics(
    *,
    focus_themes: list[str],
    match: dict[str, object],
) -> list[str]:
    return _controlled_review_topics(
        focus_themes,
        match.get("matched_topic", ""),
    )


def _controlled_review_topics(*groups: object) -> list[str]:
    topics = []
    seen = set()
    for group in groups:
        for value in _iter_review_topic_values(group):
            topic = terminal_safe(value).strip().lower().replace(" ", "_")
            if topic not in PAIN_TOPICS or topic in seen:
                continue
            seen.add(topic)
            topics.append(topic)
    return topics


def _iter_review_topic_values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(
            item
            for group_item in value
            for item in _iter_review_topic_values(group_item)
        )
    return (str(value),)


def _profile_ordered_opportunities(
    opportunities: list[dict[str, object]],
    opportunity_state: dict[str, dict[str, object]],
    *,
    has_focus: bool,
) -> list[dict[str, object]]:
    if not has_focus:
        return opportunities

    def sort_key(indexed_item: tuple[int, dict[str, object]]) -> tuple[int, int]:
        index, item = indexed_item
        state = opportunity_state.get(str(item.get("opportunity_id", "")), {})
        matched = bool(state.get("matched_themes"))
        avoided = bool(state.get("avoid_themes"))
        if matched and not avoided:
            rank = 0
        elif matched and avoided:
            rank = 1
        elif not avoided:
            rank = 2
        else:
            rank = 3
        return (rank, index)

    return [
        item
        for _index, item in sorted(
            enumerate(opportunities),
            key=sort_key,
        )
    ]


def _profile_now_priority(
    index: int,
    item_profile: dict[str, object],
    *,
    has_focus: bool,
) -> str:
    if has_focus:
        if item_profile.get("avoid_themes"):
            return "P2"
        if item_profile.get("matched_themes"):
            return "P0" if index <= 3 else "P1"
        return "P2"
    return "P0" if index == 1 else "P1"


def _profile_now_reason(item_profile: dict[str, object]) -> str:
    parts = []
    matched_themes = list(item_profile.get("matched_themes", []))
    avoided_themes = list(item_profile.get("avoid_themes", []))
    if matched_themes:
        parts.append(f"profile_focus={_join_profile_values(matched_themes)}.")
    if avoided_themes:
        parts.append(
            f"avoid_themes={_join_profile_values(avoided_themes)}; priority lowered, evidence kept."
        )
    return " ".join(parts)


def _merge_evidence_aliases(items: list[dict[str, object]]) -> list[str]:
    aliases = []
    seen = set()
    for item in items:
        for alias in item.get("evidence_aliases", []):
            text = terminal_safe(alias)
            if not text or text in seen:
                continue
            seen.add(text)
            aliases.append(text)
    return aliases[:12]


def _unique_profile_values(values: object) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = terminal_safe(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _profile_values(profile: dict[str, object], key: str) -> list[str]:
    value = profile.get(key, [])
    if not isinstance(value, list):
        return []
    return [terminal_safe(item) for item in value if str(item).strip()]


def _join_profile_values(values: list[str]) -> str:
    return ", ".join(values[:5])


def _fallback_focus_action(
    focus_themes: list[str],
    target_segments: list[str],
) -> str:
    if focus_themes and target_segments:
        return (
            "Искать новые evidence под фокус "
            f"{_join_profile_values(focus_themes)} для {_join_profile_values(target_segments)}."
        )
    if focus_themes:
        return f"Искать новые evidence под фокус: {_join_profile_values(focus_themes)}."
    if target_segments:
        return f"Искать evidence для сегмента: {_join_profile_values(target_segments)}."
    return "Сформулировать фокус-темы и первый сегмент в project profile."


def _profile_applicability(
    project_name: str,
    target_segments: list[str],
    offer_types: list[str],
) -> str:
    parts = [
        f"Для {project_name}: использовать как фильтр при выборе следующей продуктовой гипотезы."
    ]
    if target_segments:
        parts.append(f"Первый сегмент: {_join_profile_values(target_segments)}.")
    if offer_types:
        parts.append(f"Проверить упаковку: {_join_profile_values(offer_types)}.")
    return " ".join(parts)


def _project_fit_block(title: str, items: list[str], why: str) -> dict[str, object]:
    return {
        "title": title,
        "items": items or ["Не задано"],
        "why": why,
    }


def _profile_principles(
    decision_criteria: list[str],
    design_preferences: list[str],
) -> list[str]:
    principles = [
        "Сначала evidence в чате, потом продуктовая гипотеза.",
        "Не строить MVP, если данные для проверки недоступны.",
        "Показывать путь от message IDs к выводу.",
        "Держать raw Telegram data локально.",
        "После manual review перегенерировать сайт.",
    ]
    principles.extend(
        f"Критерий решения: {item}." for item in decision_criteria[:5]
    )
    principles.extend(
        f"Предпочтение продукта: {item}." for item in design_preferences[:5]
    )
    return principles


def _format_site_datetime(value: str) -> tuple[str, str]:
    if not value:
        return "unknown", ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return terminal_safe(value), ""
    return parsed.strftime("%d.%m.%Y"), parsed.strftime("%H:%M")


def _csv_values_from_db(value: object) -> tuple[str, ...]:
    seen = set()
    result = []
    for part in str(value or "").split(","):
        text = part.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(terminal_safe(text))
    return tuple(result)


def _topic_values_from_db(value: object) -> tuple[str, ...]:
    topics = []
    seen = set()
    for group in str(value or "").split(","):
        for topic in group.split("|"):
            cleaned = topic.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            topics.append(terminal_safe(cleaned))
    return tuple(topics)


def _tool_rating(trust_level: str, payment_status: str) -> int:
    if trust_level == "strong":
        return 5
    if trust_level == "medium":
        return 4
    if payment_status == "trust_signals_present":
        return 3
    return 2


def _tool_verdict(payment_status: str) -> str:
    if payment_status == "trust_signals_present":
        return "Проверить как доказательство willingness_to_pay."
    if payment_status == "ad_only_unproven":
        return "Считать рекламным сигналом, не доказательством оплаты."
    return "Слабый сигнал, нужна ручная проверка."


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


def validate_report_path(
    output_path: Path,
    *,
    allow_external_report: bool = False,
) -> None:
    if output_path.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Report output path must end with .html or .htm")

    if allow_external_report:
        return

    resolved_path = output_path.resolve()
    try:
        resolved_path.relative_to(Path("data/reports").resolve())
        return
    except ValueError:
        pass

    try:
        resolved_path.relative_to(Path("tests").resolve())
        if output_path.name.startswith("_tmp") and output_path.suffix.lower() in {
            ".html",
            ".htm",
        }:
            return
    except ValueError:
        pass

    raise ValueError(
        "Refusing to write a generated report outside data/reports by default. "
        "Use data/reports/, a tests/_tmp*.html fixture report, or pass "
        "--allow-external-report for explicit local-only external output."
    )


def validate_site_dir_path(
    output_dir: Path,
    *,
    allow_external_site: bool = False,
) -> None:
    if output_dir.suffix.lower() in {".html", ".htm", ".sqlite", ".db"}:
        raise ValueError("Site output must be a directory path, not a file path.")

    if allow_external_site:
        return

    resolved_path = output_dir.resolve()
    try:
        resolved_path.relative_to(Path("data/reports").resolve())
        return
    except ValueError:
        pass

    try:
        resolved_path.relative_to(Path("tests").resolve())
        if output_dir.name.startswith("_tmp"):
            return
    except ValueError:
        pass

    raise ValueError(
        "Refusing to write a generated site outside data/reports by default. "
        "Use data/reports/, a tests/_tmp* fixture site, or pass "
        "--allow-external-site for explicit local-only external output."
    )


def validate_project_profile_template_path(
    output_path: Path,
    *,
    allow_external_profile: bool = False,
) -> None:
    if output_path.suffix.lower() != ".json":
        raise ValueError("Project profile template output path must end with .json")

    if allow_external_profile:
        return

    resolved_path = output_path.resolve()
    try:
        resolved_path.relative_to(Path("data/reports").resolve())
        return
    except ValueError:
        pass

    try:
        resolved_path.relative_to(Path("tests").resolve())
        if output_path.name.startswith("_tmp"):
            return
    except ValueError:
        pass

    raise ValueError(
        "Refusing to write a project profile template outside data/reports by default. "
        "Use data/reports/, a tests/_tmp*.json fixture profile, or pass "
        "--allow-external-profile for explicit local-only external output."
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
