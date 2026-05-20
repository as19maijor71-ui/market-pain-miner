from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import chain

from app.clusters import detect_problem_marker_matches
from app.core.models import ClusterRecord, SolutionRecord
from app.scoring.opportunity import OpportunityScore


UNKNOWN = "unknown"
MAX_OPPORTUNITY_CARDS = 50
CARD_FIELDS = (
    "problem",
    "audience",
    "frequency",
    "current_workaround",
    "ready_solutions",
    "first_mvp",
    "payment_reason",
    "complexity",
    "risk",
    "score",
)

TIME_OR_MONEY_MARKERS = (
    "час",
    "полдня",
    "долго",
    "дорого",
    "деньг",
    "потер",
    "уходит в минус",
    "маржа в минус",
)
REPEATED_WORKFLOW_MARKERS = (
    "каждый раз",
    "каждый день",
    "ежеднев",
    "регулярно",
    "постоянно",
)
MANAGER_OR_CLIENT_MARKERS = (
    "менеджер",
    "клиент",
    "отчет клиент",
    "отчеты клиент",
    "агентств",
    "агенц",
)

MVP_BY_MARKER = {
    "stock_reconciliation": "stock_reconciliation_checker",
    "margin_calculation": "margin_fee_calculator",
    "ad_budget_leak": "ad_budget_leak_monitor",
    "supply_acceptance_delay": "supply_status_tracker",
    "card_content_drop": "card_content_change_monitor",
    "review_rating_issue": "review_question_response_queue",
    "price_discount_confusion": "price_promo_margin_checker",
    "penalty_blocker": "penalty_claim_tracker",
    "api_integration_break": "api_health_checker",
    "client_reporting_manual": "client_reporting_automation",
    "manual_automation_gap": "workflow_automation_bot",
}
COMPLEXITY_BY_MARKER = {
    "stock_reconciliation": "medium",
    "margin_calculation": "low",
    "ad_budget_leak": "medium",
    "supply_acceptance_delay": "medium",
    "card_content_drop": "medium",
    "review_rating_issue": "medium",
    "price_discount_confusion": "medium",
    "penalty_blocker": "medium",
    "api_integration_break": "high",
    "client_reporting_manual": "medium",
    "manual_automation_gap": "medium",
}
RISK_BY_MARKER = {
    "stock_reconciliation": "marketplace_data_quality_and_export_changes",
    "margin_calculation": "fee_promo_logic_changes",
    "ad_budget_leak": "ad_platform_metric_changes",
    "supply_acceptance_delay": "limited_access_to_operational_status",
    "card_content_drop": "marketplace_rules_and_seo_changes",
    "review_rating_issue": "marketplace_policy_and_response_limits",
    "price_discount_confusion": "promo_and_spp_rule_changes",
    "penalty_blocker": "legal_or_support_process_uncertainty",
    "api_integration_break": "api_access_and_token_lifecycle",
    "client_reporting_manual": "report_template_variance_by_client",
    "manual_automation_gap": "workflow_variance_between_operators",
}
MVP_SPEED_BY_MARKER = {
    "stock_reconciliation": 3,
    "margin_calculation": 4,
    "ad_budget_leak": 3,
    "supply_acceptance_delay": 2,
    "card_content_drop": 3,
    "review_rating_issue": 3,
    "price_discount_confusion": 3,
    "penalty_blocker": 2,
    "api_integration_break": 2,
    "client_reporting_manual": 3,
    "manual_automation_gap": 3,
}
DEFENSIBILITY_BY_MARKER = {
    "stock_reconciliation": 3,
    "margin_calculation": 2,
    "ad_budget_leak": 3,
    "supply_acceptance_delay": 3,
    "card_content_drop": 3,
    "review_rating_issue": 3,
    "price_discount_confusion": 3,
    "penalty_blocker": 3,
    "api_integration_break": 4,
    "client_reporting_manual": 3,
    "manual_automation_gap": 2,
}
DATA_ACCESS_BY_MARKER = {
    "stock_reconciliation": 3,
    "margin_calculation": 3,
    "ad_budget_leak": 3,
    "supply_acceptance_delay": 2,
    "card_content_drop": 3,
    "review_rating_issue": 3,
    "price_discount_confusion": 3,
    "penalty_blocker": 2,
    "api_integration_break": 2,
    "client_reporting_manual": 3,
    "manual_automation_gap": 3,
}


@dataclass(frozen=True)
class OpportunityEvidence:
    field: str
    source_message_ids: tuple[str, ...]
    label: str
    reason: str


@dataclass(frozen=True)
class OpportunityCard:
    opportunity_id: str
    cluster_id: str
    support_status: str
    problem: str
    audience: str
    frequency: str
    current_workaround: str
    ready_solutions: str
    first_mvp: str
    payment_reason: str
    complexity: str
    risk: str
    score: OpportunityScore
    evidence: tuple[OpportunityEvidence, ...]


@dataclass(frozen=True)
class PaymentSignals:
    value: str
    evidence: tuple[OpportunityEvidence, ...]
    has_solution_trust: bool
    has_time_or_money: bool
    has_repeated_workflow: bool
    has_manager_scenario: bool


def build_opportunity_cards(
    clusters: list[ClusterRecord] | tuple[ClusterRecord, ...],
    solutions: list[SolutionRecord] | tuple[SolutionRecord, ...],
    *,
    limit: int = 5,
) -> tuple[OpportunityCard, ...]:
    if limit <= 0:
        raise ValueError("limit must be greater than 0")
    if limit > MAX_OPPORTUNITY_CARDS:
        raise ValueError(f"limit must be <= {MAX_OPPORTUNITY_CARDS}")

    cards = [
        _build_card(cluster, _matching_solutions(cluster, solutions))
        for cluster in clusters
        if cluster.support_status in {"supported", "weak_signal"}
    ]
    sorted_cards = sorted(
        cards,
        key=lambda card: (
            -card.score.total,
            -card.score.frequency,
            card.support_status != "supported",
            card.cluster_id,
        ),
    )
    return tuple(
        replace(card, opportunity_id=f"opportunity{index}")
        for index, card in enumerate(sorted_cards[:limit], start=1)
    )


def _build_card(
    cluster: ClusterRecord,
    matched_solutions: tuple[SolutionRecord, ...],
) -> OpportunityCard:
    evidence: list[OpportunityEvidence] = []

    problem = cluster.problem_label if cluster.evidence else UNKNOWN
    if problem != UNKNOWN:
        evidence.append(
            _cluster_evidence(
                cluster,
                field="problem",
                label=f"problem_marker:{cluster.problem_marker}",
                reason="pain/question cluster matched an explicit problem marker",
            )
        )

    frequency = (
        f"unique_count={cluster.unique_count}; "
        f"raw_count={cluster.raw_count}; "
        f"duplicate_count={cluster.duplicate_count}; "
        f"weaker_evidence_count={cluster.weaker_evidence_count}; "
        f"support_status={cluster.support_status}"
    )
    evidence.append(
        _cluster_evidence(
            cluster,
            field="frequency",
            label="frequency:deduplicated_unique_count",
            reason="frequency is counted from unique_count, with weak evidence flags shown separately",
        )
    )

    audience, audience_evidence = _audience(cluster, matched_solutions)
    evidence.extend(audience_evidence)

    workaround, workaround_evidence = _current_workaround(cluster)
    evidence.extend(workaround_evidence)

    ready_solutions, solution_evidence = _ready_solutions(matched_solutions)
    evidence.extend(solution_evidence)

    first_mvp, mvp_evidence = _first_mvp(cluster, matched_solutions)
    evidence.extend(mvp_evidence)

    payment = _payment_reason(cluster, matched_solutions)
    evidence.extend(payment.evidence)

    complexity = COMPLEXITY_BY_MARKER.get(cluster.problem_marker, UNKNOWN)
    if complexity != UNKNOWN:
        evidence.append(
            _cluster_evidence(
                cluster,
                field="complexity",
                label=f"complexity_rule:{cluster.problem_marker}",
                reason="controlled implementation-complexity rule for the explicit problem marker",
            )
        )

    risk = RISK_BY_MARKER.get(cluster.problem_marker, UNKNOWN)
    if risk != UNKNOWN:
        evidence.append(
            _cluster_evidence(
                cluster,
                field="risk",
                label=f"risk_rule:{cluster.problem_marker}",
                reason="controlled risk rule for the explicit problem marker",
            )
        )

    score = _score(cluster, matched_solutions, payment, first_mvp != UNKNOWN)
    evidence.append(
        OpportunityEvidence(
            field="score",
            source_message_ids=_merge_message_ids(
                cluster.evidence_message_ids,
                *_trusted_solution_message_ids(matched_solutions),
            ),
            label="score:unique_count_supported_cluster_weak_evidence_payment_rules",
            reason=(
                "frequency uses unique_count; supported clusters score above weak signals; "
                "weak/duplicate/forwarded evidence reduces confidence; ad-only solutions "
                "do not count as payment proof"
            ),
        )
    )

    return OpportunityCard(
        opportunity_id="",
        cluster_id=cluster.cluster_id,
        support_status=cluster.support_status,
        problem=problem,
        audience=audience,
        frequency=frequency,
        current_workaround=workaround,
        ready_solutions=ready_solutions,
        first_mvp=first_mvp,
        payment_reason=payment.value,
        complexity=complexity,
        risk=risk,
        score=score,
        evidence=tuple(evidence),
    )


def _matching_solutions(
    cluster: ClusterRecord,
    solutions: list[SolutionRecord] | tuple[SolutionRecord, ...],
) -> tuple[SolutionRecord, ...]:
    matched = []
    for solution in solutions:
        promises = set(_csv_values(solution.promise))
        if cluster.problem_marker in promises:
            matched.append(solution)
            continue
        for mention in solution.mentions:
            marker_keys = {
                match.marker.key
                for match in detect_problem_marker_matches(
                    mention.normalized_text or mention.promise
                )
                if match.marker.topic == cluster.topic
            }
            if cluster.problem_marker in marker_keys:
                matched.append(solution)
                break
    return tuple(matched)


def _audience(
    cluster: ClusterRecord,
    matched_solutions: tuple[SolutionRecord, ...],
) -> tuple[str, tuple[OpportunityEvidence, ...]]:
    solution_audiences = sorted(
        {
            audience
            for solution in matched_solutions
            for audience in solution.target_audience
        }
    )
    if solution_audiences:
        return (
            ",".join(solution_audiences),
            (
                OpportunityEvidence(
                    field="audience",
                    source_message_ids=_merge_message_ids(
                        *(
                            solution.source_message_ids
                            for solution in matched_solutions
                            if solution.target_audience
                        )
                    ),
                    label="audience:solution_target_audience",
                    reason="matched solution records contain controlled target-audience labels",
                ),
            ),
        )

    if cluster.problem_marker == "client_reporting_manual":
        return (
            "marketplace_managers,agencies",
            (
                _cluster_evidence(
                    cluster,
                    field="audience",
                    label="audience:manager_or_agency_reporting_marker",
                    reason="problem marker explicitly describes client or manager reporting",
                ),
            ),
        )

    return UNKNOWN, ()


def _current_workaround(
    cluster: ClusterRecord,
) -> tuple[str, tuple[OpportunityEvidence, ...]]:
    manual_table_refs = _cluster_refs_where(
        cluster,
        lambda item: "вручную" in item.normalized_text and "таблиц" in item.normalized_text,
    )
    if manual_table_refs:
        return (
            "manual_spreadsheet_or_cabinet_reconciliation",
            (
                OpportunityEvidence(
                    field="current_workaround",
                    source_message_ids=manual_table_refs,
                    label="workaround:manual_spreadsheet_or_cabinet",
                    reason="cluster evidence mentions manual work together with spreadsheet/cabinet reconciliation",
                ),
            ),
        )

    manual_refs = _cluster_refs_where(
        cluster,
        lambda item: "вручную" in item.normalized_text,
    )
    if manual_refs:
        return (
            "manual_workflow",
            (
                OpportunityEvidence(
                    field="current_workaround",
                    source_message_ids=manual_refs,
                    label="workaround:manual_workflow",
                    reason="cluster evidence mentions manual work",
                ),
            ),
        )

    return UNKNOWN, ()


def _ready_solutions(
    matched_solutions: tuple[SolutionRecord, ...],
) -> tuple[str, tuple[OpportunityEvidence, ...]]:
    if not matched_solutions:
        return UNKNOWN, ()

    values = [
        (
            f"{solution.solution_id}:"
            f"{solution.solution_type}/"
            f"{solution.payment_status}"
        )
        for solution in matched_solutions
    ]
    return (
        "; ".join(values),
        (
            OpportunityEvidence(
                field="ready_solutions",
                source_message_ids=_merge_message_ids(
                    *(solution.source_message_ids for solution in matched_solutions)
                ),
                label="ready_solutions:matched_solution_records",
                reason="solution records match the same explicit problem marker or topic-marker evidence",
            ),
        ),
    )


def _first_mvp(
    cluster: ClusterRecord,
    matched_solutions: tuple[SolutionRecord, ...],
) -> tuple[str, tuple[OpportunityEvidence, ...]]:
    mvp = MVP_BY_MARKER.get(cluster.problem_marker, UNKNOWN)
    if mvp == UNKNOWN:
        return UNKNOWN, ()
    if cluster.support_status != "supported" and not matched_solutions:
        return UNKNOWN, ()

    evidence_ids = _merge_message_ids(
        cluster.evidence_message_ids,
        *(solution.source_message_ids for solution in matched_solutions),
    )
    return (
        mvp,
        (
            OpportunityEvidence(
                field="first_mvp",
                source_message_ids=evidence_ids,
                label=f"mvp_rule:{cluster.problem_marker}",
                reason="controlled MVP rule backed by the problem cluster and any matched solution records",
            ),
        ),
    )


def _payment_reason(
    cluster: ClusterRecord,
    matched_solutions: tuple[SolutionRecord, ...],
) -> PaymentSignals:
    evidence: list[OpportunityEvidence] = []
    reasons: list[str] = []

    trusted_solutions = [
        solution
        for solution in matched_solutions
        if solution.payment_status == "trust_signals_present"
        and solution.trust_payment_signals
    ]
    if trusted_solutions:
        reasons.append("solution_trust_payment_signals")
        labels = sorted(
            {
                signal
                for solution in trusted_solutions
                for signal in solution.trust_payment_signals
            }
        )
        evidence.append(
            OpportunityEvidence(
                field="payment_reason",
                source_message_ids=_merge_message_ids(
                    *(solution.source_message_ids for solution in trusted_solutions)
                ),
                label="payment:" + ",".join(labels),
                reason="matched solution records contain trust/payment signals, not just ad signals",
            )
        )

    time_refs = _cluster_refs_where(
        cluster,
        lambda item: _contains_any(item.normalized_text, TIME_OR_MONEY_MARKERS),
    )
    if time_refs:
        reasons.append("time_or_money_loss")
        evidence.append(
            OpportunityEvidence(
                field="payment_reason",
                source_message_ids=time_refs,
                label="payment:time_or_money_loss",
                reason="pain evidence mentions time, money, cost, loss, or negative margin",
            )
        )

    repeated_refs = _cluster_refs_where(
        cluster,
        lambda item: _contains_any(item.normalized_text, REPEATED_WORKFLOW_MARKERS),
    )
    if repeated_refs:
        reasons.append("repeated_workflow")
        evidence.append(
            OpportunityEvidence(
                field="payment_reason",
                source_message_ids=repeated_refs,
                label="payment:repeated_workflow",
                reason="pain evidence describes a repeated workflow",
            )
        )

    manager_refs = _cluster_refs_where(
        cluster,
        lambda item: _contains_any(item.normalized_text, MANAGER_OR_CLIENT_MARKERS),
    )
    manager_solution_refs = _merge_message_ids(
        *(
            solution.source_message_ids
            for solution in trusted_solutions
            if set(solution.target_audience) & {"marketplace_managers", "agencies"}
        )
    )
    if manager_refs or manager_solution_refs:
        reasons.append("manager_agency_client_reporting_scenario")
        evidence.append(
            OpportunityEvidence(
                field="payment_reason",
                source_message_ids=_merge_message_ids(manager_refs, manager_solution_refs),
                label="payment:manager_agency_client_reporting",
                reason="evidence points to manager, agency, or client reporting work",
            )
        )

    value = ",".join(dict.fromkeys(reasons)) if reasons else UNKNOWN
    return PaymentSignals(
        value=value,
        evidence=tuple(evidence),
        has_solution_trust=bool(trusted_solutions),
        has_time_or_money=bool(time_refs),
        has_repeated_workflow=bool(repeated_refs),
        has_manager_scenario=bool(manager_refs or manager_solution_refs),
    )


def _score(
    cluster: ClusterRecord,
    matched_solutions: tuple[SolutionRecord, ...],
    payment: PaymentSignals,
    has_first_mvp: bool,
) -> OpportunityScore:
    frequency = _score_frequency(cluster.unique_count)
    weak_penalty = _weak_evidence_penalty(cluster)
    support_bonus = 1 if cluster.support_status == "supported" else 0

    urgency = 2 + support_bonus
    if payment.has_time_or_money:
        urgency += 1
    if payment.has_repeated_workflow:
        urgency += 1
    urgency = _bounded_score(urgency - weak_penalty)

    willingness_to_pay = 1
    if payment.has_solution_trust:
        willingness_to_pay += 2
    if payment.has_time_or_money:
        willingness_to_pay += 1
    if payment.has_repeated_workflow:
        willingness_to_pay += 1
    if payment.has_manager_scenario:
        willingness_to_pay += 1
    willingness_to_pay = _bounded_score(willingness_to_pay)

    mvp_speed = MVP_SPEED_BY_MARKER.get(cluster.problem_marker, 1)
    if not has_first_mvp:
        mvp_speed = 1

    repeatability = 2 + support_bonus
    if payment.has_repeated_workflow:
        repeatability += 1
    if matched_solutions:
        repeatability += 1
    repeatability = _bounded_score(repeatability - weak_penalty)

    defensibility = DEFENSIBILITY_BY_MARKER.get(cluster.problem_marker, 1)
    data_access = DATA_ACCESS_BY_MARKER.get(cluster.problem_marker, 1)

    return OpportunityScore(
        frequency=frequency,
        urgency=urgency,
        willingness_to_pay=willingness_to_pay,
        mvp_speed=_bounded_score(mvp_speed),
        repeatability=repeatability,
        defensibility=_bounded_score(defensibility),
        data_access=_bounded_score(data_access),
    )


def _score_frequency(unique_count: int) -> int:
    if unique_count >= 10:
        return 5
    if unique_count >= 6:
        return 4
    if unique_count >= 3:
        return 3
    if unique_count >= 2:
        return 2
    return 1


def _weak_evidence_penalty(cluster: ClusterRecord) -> int:
    return 1 if cluster.weaker_evidence_count > 0 else 0


def _bounded_score(value: int) -> int:
    return max(1, min(5, value))


def _cluster_evidence(
    cluster: ClusterRecord,
    *,
    field: str,
    label: str,
    reason: str,
) -> OpportunityEvidence:
    return OpportunityEvidence(
        field=field,
        source_message_ids=cluster.evidence_message_ids,
        label=label,
        reason=reason,
    )


def _cluster_refs_where(
    cluster: ClusterRecord,
    predicate: Callable[[object], bool],
) -> tuple[str, ...]:
    refs = [
        item.message_ref
        for item in cluster.evidence
        if predicate(item)
    ]
    return _merge_message_ids(refs)


def _trusted_solution_message_ids(
    matched_solutions: tuple[SolutionRecord, ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        solution.source_message_ids
        for solution in matched_solutions
        if solution.payment_status == "trust_signals_present"
    )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split(",") if item)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _merge_message_ids(*groups: object) -> tuple[str, ...]:
    seen = set()
    merged = []
    for value in chain.from_iterable(_iter_group(group) for group in groups):
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return tuple(merged)


def _iter_group(group: object) -> tuple[str, ...]:
    if group is None:
        return ()
    if isinstance(group, str):
        return (group,)
    return tuple(str(item) for item in group)
