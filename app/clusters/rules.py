from __future__ import annotations

from dataclasses import dataclass

from app.clusters.problem_markers import PROBLEM_MARKERS
from app.core.models import (
    ClusterBuildResult,
    ClusterEvidence,
    ClusterNoiseGroup,
    ClusterRecord,
    ClusterRejection,
    ClusterSourceMessage,
    ProblemMarkerDefinition,
)
from app.normalization import normalize_message_text


MIN_SUPPORTED_UNIQUE_MESSAGES = 3
CLUSTERABLE_CATEGORIES = frozenset({"pain", "question"})


@dataclass(frozen=True)
class ProblemMarkerMatch:
    marker: ProblemMarkerDefinition
    synonym: str


def build_clusters(
    messages: list[ClusterSourceMessage],
    *,
    min_supported_unique: int = MIN_SUPPORTED_UNIQUE_MESSAGES,
) -> list[ClusterRecord]:
    return list(
        build_cluster_report(
            messages,
            min_supported_unique=min_supported_unique,
        ).clusters
    )


def build_cluster_report(
    messages: list[ClusterSourceMessage],
    *,
    min_supported_unique: int = MIN_SUPPORTED_UNIQUE_MESSAGES,
) -> ClusterBuildResult:
    accepted, rejected, marker_lookup = _collect_cluster_candidates(messages)

    clusters = [
        _build_cluster(
            key,
            items,
            rejected.get((key[1], key[2]), []),
            min_supported_unique=min_supported_unique,
        )
        for key, items in accepted.items()
    ]
    sorted_clusters = tuple(
        sorted(
            clusters,
            key=lambda cluster: (
                0 if cluster.support_status == "supported" else 1,
                cluster.category,
                cluster.topic,
                cluster.problem_marker,
            ),
        )
    )
    accepted_marker_keys = {(key[1], key[2]) for key in accepted}
    orphan_noise = tuple(
        _build_noise_group(key, items, marker_lookup[key])
        for key, items in sorted(rejected.items())
        if key not in accepted_marker_keys
    )
    return ClusterBuildResult(clusters=sorted_clusters, orphan_noise=orphan_noise)


def _collect_cluster_candidates(
    messages: list[ClusterSourceMessage],
) -> tuple[
    dict[tuple[str, str, str], list[tuple[ClusterSourceMessage, ProblemMarkerMatch]]],
    dict[tuple[str, str], list[ClusterRejection]],
    dict[tuple[str, str], ProblemMarkerDefinition],
]:
    accepted: dict[tuple[str, str, str], list[tuple[ClusterSourceMessage, ProblemMarkerMatch]]] = {}
    rejected: dict[tuple[str, str], list[ClusterRejection]] = {}
    marker_lookup: dict[tuple[str, str], ProblemMarkerDefinition] = {}

    for message in messages:
        matches = detect_problem_marker_matches(message.normalized_text or message.text)
        topic_set = set(message.topics)
        for match in matches:
            topic = match.marker.topic
            if topic not in topic_set:
                continue

            topic_marker_key = (topic, match.marker.key)
            marker_lookup[topic_marker_key] = match.marker
            if message.category in CLUSTERABLE_CATEGORIES:
                cluster_key = (message.category, topic, match.marker.key)
                accepted.setdefault(cluster_key, []).append((message, match))
            else:
                rejected.setdefault(topic_marker_key, []).append(
                    ClusterRejection(
                        chat_id=message.chat_id,
                        msg_id=message.msg_id,
                        message_ref=message_ref(message.chat_id, message.msg_id),
                        category=message.category,
                        matched_synonym=match.synonym,
                        reason="category_not_clustered",
                    )
                )

    return accepted, rejected, marker_lookup


def detect_problem_marker_matches(text: str) -> tuple[ProblemMarkerMatch, ...]:
    normalized = normalize_message_text(text)
    matches: list[ProblemMarkerMatch] = []
    for marker in PROBLEM_MARKERS:
        for synonym in marker.synonyms:
            if synonym in normalized:
                matches.append(ProblemMarkerMatch(marker=marker, synonym=synonym))
                break
    return tuple(matches)


def message_ref(chat_id: str, msg_id: int) -> str:
    return f"{chat_id}:{msg_id}"


def _build_cluster(
    key: tuple[str, str, str],
    items: list[tuple[ClusterSourceMessage, ProblemMarkerMatch]],
    rejected: list[ClusterRejection],
    *,
    min_supported_unique: int,
) -> ClusterRecord:
    category, topic, marker_key = key
    ordered_items = sorted(
        items,
        key=lambda item: (item[0].date, item[0].msg_id, item[0].chat_id),
    )

    evidence: list[ClusterEvidence] = []
    seen_evidence_keys: set[str] = set()
    for message, match in ordered_items:
        evidence_key = _evidence_key(message)
        is_duplicate = evidence_key in seen_evidence_keys
        seen_evidence_keys.add(evidence_key)
        evidence.append(
            ClusterEvidence(
                chat_id=message.chat_id,
                msg_id=message.msg_id,
                message_ref=message_ref(message.chat_id, message.msg_id),
                evidence_key=evidence_key,
                matched_synonym=match.synonym,
                is_forwarded=bool(message.forwarded_from),
                is_duplicate=is_duplicate,
                normalized_text=message.normalized_text,
            )
        )

    marker = ordered_items[0][1].marker
    raw_count = len(evidence)
    unique_count = len({item.evidence_key for item in evidence})
    duplicate_count = raw_count - unique_count
    weaker_evidence_count = sum(
        1 for item in evidence if item.is_forwarded or item.is_duplicate
    )
    support_status = (
        "supported" if unique_count >= min_supported_unique else "weak_signal"
    )
    matched_synonyms = sorted({item.matched_synonym for item in evidence})
    merge_reason = (
        "same category, same topic, same explicit problem marker; "
        f"category={category}; topic={topic}; problem_marker={marker_key}; "
        f"matched_synonyms={', '.join(matched_synonyms)}"
    )
    ordered_rejected = tuple(
        sorted(rejected, key=lambda item: (item.msg_id, item.chat_id, item.category))
    )

    return ClusterRecord(
        cluster_id=f"{category}:{topic}:{marker_key}",
        category=category,
        topic=topic,
        problem_marker=marker_key,
        problem_label=marker.label,
        raw_count=raw_count,
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        weaker_evidence_count=weaker_evidence_count,
        support_status=support_status,
        evidence_message_ids=tuple(item.message_ref for item in evidence),
        rejected_message_ids=tuple(item.message_ref for item in ordered_rejected),
        merge_reason=merge_reason,
        evidence=tuple(evidence),
        rejected=ordered_rejected,
    )


def _build_noise_group(
    key: tuple[str, str],
    rejected: list[ClusterRejection],
    marker: ProblemMarkerDefinition,
) -> ClusterNoiseGroup:
    ordered_rejected = tuple(
        sorted(rejected, key=lambda item: (item.msg_id, item.chat_id, item.category))
    )
    return ClusterNoiseGroup(
        topic=key[0],
        problem_marker=key[1],
        problem_label=marker.label,
        rejected_message_ids=tuple(item.message_ref for item in ordered_rejected),
        rejected=ordered_rejected,
    )


def _evidence_key(message: ClusterSourceMessage) -> str:
    if message.normalized_text:
        return message.normalized_text
    return message_ref(message.chat_id, message.msg_id)
