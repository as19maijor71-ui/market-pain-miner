from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatRecord:
    chat_id: str
    name: str
    type: str
    total_messages: int


@dataclass(frozen=True)
class MessageRecord:
    chat_id: str
    msg_id: int
    date: str
    author: str
    from_id: str
    topic_id: str | None
    reply_to: int | None
    forwarded_from: str
    text: str
    normalized_text: str
    has_photo: bool
    has_file: bool
    media_type: str
    raw_json: str


@dataclass(frozen=True)
class LabelRecord:
    chat_id: str
    msg_id: int
    category: str
    topics: list[str]
    confidence: float
    source: str
    classifier_name: str
    classifier_version: str
    run_id: str


@dataclass(frozen=True)
class ImportResult:
    chat: ChatRecord
    messages: list[MessageRecord]


@dataclass(frozen=True)
class ProblemMarkerDefinition:
    key: str
    topic: str
    label: str
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class ClusterSourceMessage:
    chat_id: str
    msg_id: int
    date: str
    category: str
    topics: tuple[str, ...]
    text: str
    normalized_text: str
    forwarded_from: str


@dataclass(frozen=True)
class ClusterEvidence:
    chat_id: str
    msg_id: int
    message_ref: str
    evidence_key: str
    matched_synonym: str
    is_forwarded: bool
    is_duplicate: bool
    normalized_text: str


@dataclass(frozen=True)
class ClusterRejection:
    chat_id: str
    msg_id: int
    message_ref: str
    category: str
    matched_synonym: str
    reason: str


@dataclass(frozen=True)
class ClusterRecord:
    cluster_id: str
    category: str
    topic: str
    problem_marker: str
    problem_label: str
    raw_count: int
    unique_count: int
    duplicate_count: int
    weaker_evidence_count: int
    support_status: str
    evidence_message_ids: tuple[str, ...]
    rejected_message_ids: tuple[str, ...]
    merge_reason: str
    evidence: tuple[ClusterEvidence, ...]
    rejected: tuple[ClusterRejection, ...]


@dataclass(frozen=True)
class ClusterNoiseGroup:
    topic: str
    problem_marker: str
    problem_label: str
    rejected_message_ids: tuple[str, ...]
    rejected: tuple[ClusterRejection, ...]


@dataclass(frozen=True)
class ClusterBuildResult:
    clusters: tuple[ClusterRecord, ...]
    orphan_noise: tuple[ClusterNoiseGroup, ...]


@dataclass(frozen=True)
class SolutionSourceMessage:
    chat_id: str
    msg_id: int
    date: str
    author: str
    from_id: str
    category: str
    topics: tuple[str, ...]
    text: str
    normalized_text: str
    forwarded_from: str


@dataclass(frozen=True)
class SolutionMention:
    chat_id: str
    msg_id: int
    message_ref: str
    author: str
    from_id: str
    category: str
    subtype: str
    flags: tuple[str, ...]
    identity_key: str
    name: str
    solution_type: str
    locators: tuple[str, ...]
    promise: str
    target_audience: tuple[str, ...]
    ad_signals: tuple[str, ...]
    price: str
    trust_payment_signals: tuple[str, ...]
    normalized_text: str
    is_forwarded: bool


@dataclass(frozen=True)
class SolutionRecord:
    solution_id: str
    identity_key: str
    primary_subtype: str
    subtypes: tuple[str, ...]
    solution_type: str
    name: str
    locators: tuple[str, ...]
    promise: str
    target_audience: tuple[str, ...]
    ad_signals: tuple[str, ...]
    price: str
    source_message_ids: tuple[str, ...]
    trust_payment_signals: tuple[str, ...]
    trust_level: str
    payment_status: str
    mentions: tuple[SolutionMention, ...]


@dataclass(frozen=True)
class SolutionBuildResult:
    records: tuple[SolutionRecord, ...]
