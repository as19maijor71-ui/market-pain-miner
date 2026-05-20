from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.models import (
    SolutionBuildResult,
    SolutionMention,
    SolutionRecord,
    SolutionSourceMessage,
)
from app.normalization import TELEGRAM_HANDLE_RE, URL_RE, normalize_message_text


SOLUTION_SUBTYPE_ORDER = (
    "affiliate_or_spam",
    "recommendation",
    "solution_ad",
    "tool_mention",
)
SOLUTION_CATEGORIES = frozenset({"solution_ad", "tool_mention"})
MARKETPLACE_NAMES = frozenset(
    {
        "api",
        "fbo",
        "fbs",
        "ozon",
        "wb",
        "wildberries",
    }
)
LATIN_NAME_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")
BOT_MARKER_RE = re.compile(r"(?<![a-zа-яё])(?:чатбот|бот(?:а|ы|ом|е)?)(?![a-zа-яё])")
PRICE_RE = re.compile(
    r"(?i)"
    r"(?:"
    r"\d[\d\s]*(?:[.,]\d+)?\s*(?:₽|руб\.?|р\.?)"
    r"(?:\s*/?\s*(?:мес|месяц|month))?"
    r"|"
    r"\d[\d\s]*(?:[.,]\d+)?\s*тыс\.?\s*(?:руб\.?|₽)?"
    r"(?:\s*/?\s*(?:мес|месяц|month))?"
    r")"
)
TYPE_MARKERS = (
    ("telegram_bot", ("бот", "t.me/", "telegram.me/", "@")),
    ("browser_extension", ("расширен", "extension")),
    ("spreadsheet", ("таблиц", "шаблон", "google sheet", "excel")),
    ("parser", ("парсер", "парсинг")),
    ("api_integration", ("api", "апи", "интеграц")),
    ("reporting_automation", ("отчет", "дашборд", "dashboard")),
    ("consulting", ("курс", "консультац", "наставник", "аудит")),
    ("analytics_service", ("сервис", "аналитик", "платформ")),
)
AUDIENCE_MARKERS = (
    ("marketplace_sellers", ("селлер", "продавц", "поставщик")),
    ("marketplace_managers", ("менеджер", "аккаунт", "клиент")),
    ("agencies", ("агентств", "агенц")),
)
AD_SIGNAL_MARKERS = (
    ("owned_solution", ("наш сервис", "наш бот", "запустили", "сделали", "сделал")),
    ("demo", ("демо", "demo")),
    ("call_to_action", ("пишите", "заявк", "в лс", "в личку")),
    ("promo_code", ("промокод", "promo")),
    ("discount", ("скидк",)),
    ("urgency", ("только сегодня", "успей", "последний день")),
    ("subscription_or_tariff", ("подписк", "тариф")),
)
AFFILIATE_OR_SPAM_MARKERS = (
    "промокод",
    "реф",
    "ref",
    "партнер",
    "партнёр",
    "affiliate",
    "скидка только сегодня",
    "только сегодня",
)
RECOMMENDATION_MARKERS = (
    "рекомендую",
    "советую",
    "пользуемся",
    "нам помог",
    "у нас работает",
)
PRICE_DISCUSSION_MARKERS = (
    "сколько стоит",
    "стоимость",
    "цена",
    "дорого",
    "дешевле",
)
COMPLAINT_MARKERS = (
    "лома",
    "глюч",
    "не работает",
    "дорого",
    "ищем альтернатив",
    "альтернативу",
    "жалоб",
)
SOLUTION_HINT_MARKERS = (
    "бот",
    "сервис",
    "дашборд",
    "отчет",
    "таблиц",
    "расширен",
    "парсер",
    "платформ",
    "подписк",
    "тариф",
)
PROMISE_LABELS = (
    ("stock_reconciliation", ("остат", "свер")),
    ("stock_reconciliation", ("остат", "расхожд")),
    ("stock_reconciliation", ("остат", "склад")),
    ("ad_reporting", ("дрр",)),
    ("ad_reporting", ("реклам", "отчет")),
    ("reporting_automation", ("отчет",)),
    ("margin_calculation", ("марж",)),
    ("price_monitoring", ("цен",)),
    ("review_management", ("отзыв",)),
    ("time_saving", ("экономит",)),
    ("automation", ("автомат",)),
)


def build_solution_report(
    messages: list[SolutionSourceMessage],
) -> SolutionBuildResult:
    mentions = [
        mention
        for message in messages
        for mention in extract_solution_mentions(message)
    ]
    grouped: dict[str, list[SolutionMention]] = {}
    for mention in mentions:
        grouped.setdefault(mention.identity_key, []).append(mention)

    records = [
        _build_solution_record(index, identity_key, group)
        for index, (identity_key, group) in enumerate(
            sorted(grouped.items(), key=_group_sort_key),
            start=1,
        )
    ]
    return SolutionBuildResult(records=tuple(records))


def extract_solution_mentions(
    message: SolutionSourceMessage,
) -> tuple[SolutionMention, ...]:
    text = message.text
    normalized = normalize_message_text(text)
    lowercase = text.lower()
    locators = _extract_locators(text)
    name = _extract_name(text, locators)
    has_named_solution = bool(locators or name)
    has_solution_hint = _has_solution_hint(lowercase, locators, name)
    has_solution_context = bool(locators or _contains_any(lowercase, SOLUTION_HINT_MARKERS))
    has_complaint = _contains_any(lowercase, COMPLAINT_MARKERS)

    if message.category not in SOLUTION_CATEGORIES and not (
        has_named_solution and has_solution_context and has_complaint
    ):
        return ()

    subtypes = _detect_subtypes(message.category, lowercase, has_solution_hint)
    if not subtypes:
        return ()

    price = _extract_price(text)
    ad_signals = _detect_ad_signals(lowercase, price)
    trust_payment_signals = _detect_trust_payment_signals(
        lowercase,
        price=price,
        has_complaint=has_complaint,
        subtypes=subtypes,
    )
    identity_key = _identity_key(name, locators)
    if not identity_key:
        identity_key = f"message:{message.chat_id}:{message.msg_id}"

    subtype = _primary_subtype(subtypes)
    flags = tuple(
        sorted(
            {
                f"category:{message.category}",
                *subtypes,
                *ad_signals,
                *trust_payment_signals,
            }
        )
    )
    return (
        SolutionMention(
            chat_id=message.chat_id,
            msg_id=message.msg_id,
            message_ref=message_ref(message.chat_id, message.msg_id),
            author=message.author,
            from_id=message.from_id,
            category=message.category,
            subtype=subtype,
            flags=flags,
            identity_key=identity_key,
            name=name,
            solution_type=_detect_solution_type(lowercase, locators),
            locators=locators,
            promise=_extract_promise(text),
            target_audience=_detect_target_audience(lowercase),
            ad_signals=ad_signals,
            price=price,
            trust_payment_signals=trust_payment_signals,
            normalized_text=normalized,
            is_forwarded=bool(message.forwarded_from),
        ),
    )


def message_ref(chat_id: str, msg_id: int) -> str:
    return f"{chat_id}:{msg_id}"


def _build_solution_record(
    index: int,
    identity_key: str,
    mentions: list[SolutionMention],
) -> SolutionRecord:
    ordered_mentions = tuple(
        sorted(mentions, key=lambda item: (item.msg_id, item.chat_id))
    )
    subtypes = _sort_subtypes(
        {
            flag
            for item in ordered_mentions
            for flag in item.flags
            if flag in SOLUTION_SUBTYPE_ORDER
        }
    )
    trust_payment_signals = set(
        signal
        for item in ordered_mentions
        for signal in item.trust_payment_signals
    )
    if _has_repeated_independent_mentions(ordered_mentions):
        trust_payment_signals.add("repeated_independent_mention")

    merged_trust_payment_signals = _sort_trust_signals(trust_payment_signals)
    trust_level = _trust_level(merged_trust_payment_signals)
    ad_signals = _merge_values(
        signal for item in ordered_mentions for signal in item.ad_signals
    )

    return SolutionRecord(
        solution_id=f"solution{index}",
        identity_key=identity_key,
        primary_subtype=_primary_subtype(subtypes),
        subtypes=subtypes,
        solution_type=_first_known(item.solution_type for item in ordered_mentions),
        name=_first_non_empty(item.name for item in ordered_mentions),
        locators=_merge_values(
            locator for item in ordered_mentions for locator in item.locators
        ),
        promise=_first_non_empty(item.promise for item in ordered_mentions),
        target_audience=_merge_values(
            audience for item in ordered_mentions for audience in item.target_audience
        ),
        ad_signals=ad_signals,
        price=_first_non_empty(item.price for item in ordered_mentions),
        source_message_ids=tuple(item.message_ref for item in ordered_mentions),
        trust_payment_signals=merged_trust_payment_signals,
        trust_level=trust_level,
        payment_status=_payment_status(
            trust_level=trust_level,
            ad_signals=ad_signals,
            has_ad_subtype="solution_ad" in subtypes,
        ),
        mentions=ordered_mentions,
    )


def _group_sort_key(item: tuple[str, list[SolutionMention]]) -> tuple[int, str]:
    identity_key, mentions = item
    trust_signals = {
        signal for mention in mentions for signal in mention.trust_payment_signals
    }
    if _has_repeated_independent_mentions(tuple(mentions)):
        trust_signals.add("repeated_independent_mention")
    return (-len(trust_signals), identity_key)


def _detect_subtypes(
    category: str,
    text: str,
    has_solution_hint: bool,
) -> tuple[str, ...]:
    subtypes = set()
    if category == "solution_ad":
        subtypes.add("solution_ad")
    if category == "tool_mention":
        subtypes.add("tool_mention")
    if _contains_any(text, AFFILIATE_OR_SPAM_MARKERS):
        subtypes.add("affiliate_or_spam")
    if _contains_any(text, RECOMMENDATION_MARKERS):
        subtypes.add("recommendation")
    if has_solution_hint and _contains_any(text, COMPLAINT_MARKERS):
        subtypes.add("tool_mention")
    return _sort_subtypes(subtypes)


def _detect_solution_type(text: str, locators: tuple[str, ...]) -> str:
    locator_text = " ".join(locators).lower()
    combined = f"{text} {locator_text}"
    for solution_type, markers in TYPE_MARKERS:
        if _contains_any(combined, markers):
            return solution_type
    return "unknown"


def _detect_target_audience(text: str) -> tuple[str, ...]:
    found = [
        audience
        for audience, markers in AUDIENCE_MARKERS
        if _contains_any(text, markers)
    ]
    return tuple(found)


def _detect_ad_signals(text: str, price: str) -> tuple[str, ...]:
    signals = {
        signal
        for signal, markers in AD_SIGNAL_MARKERS
        if _contains_any(text, markers)
    }
    if price:
        signals.add("price_visible")
    if _contains_any(text, AFFILIATE_OR_SPAM_MARKERS):
        signals.add("affiliate_marker")
    return tuple(sorted(signals))


def _detect_trust_payment_signals(
    text: str,
    *,
    price: str,
    has_complaint: bool,
    subtypes: tuple[str, ...],
) -> tuple[str, ...]:
    signals = set()
    has_price_discussion = _contains_any(text, PRICE_DISCUSSION_MARKERS)
    has_ad_subtype = "solution_ad" in subtypes
    has_participant_context = (
        "recommendation" in subtypes
        or has_price_discussion
        or has_complaint
    )
    if price and has_price_discussion:
        signals.add("price_discussion")
    if (
        ("подписк" in text or "тариф" in text)
        and (not has_ad_subtype or has_participant_context)
    ):
        signals.add("explicit_paid_subscription")
    if _contains_any(text, RECOMMENDATION_MARKERS):
        signals.add("recommendation_from_participant")
    if has_complaint:
        signals.add("complaint_about_alternative")
    return _sort_trust_signals(signals)


def _extract_locators(text: str) -> tuple[str, ...]:
    locators = []
    for match in URL_RE.finditer(text):
        locators.append(_clean_locator(match.group(0)))
    for match in TELEGRAM_HANDLE_RE.finditer(text):
        locators.append(_clean_locator(match.group(0)))
    return _merge_values(locators)


def _extract_name(text: str, locators: tuple[str, ...]) -> str:
    candidates = []
    for match in LATIN_NAME_RE.finditer(text):
        candidate = match.group(0)
        if _is_solution_name_candidate(candidate):
            candidates.append(candidate)
    if candidates:
        return candidates[-1]

    for locator in locators:
        if locator.startswith("@"):
            return locator[1:]
        domain_name = _domain_name(locator)
        if domain_name:
            return domain_name
    return ""


def _is_solution_name_candidate(candidate: str) -> bool:
    lowered = candidate.lower()
    return (
        lowered not in MARKETPLACE_NAMES
        and not lowered.startswith("partner")
        and not lowered.startswith("promo")
    )


def _extract_price(text: str) -> str:
    match = PRICE_RE.search(text)
    if not match:
        return ""
    return " ".join(match.group(0).split())


def _extract_promise(text: str) -> str:
    lowered = normalize_message_text(text)
    labels = []
    for label, markers in PROMISE_LABELS:
        if label in labels:
            continue
        if all(marker in lowered for marker in markers):
            labels.append(label)
    if labels:
        return ",".join(labels)
    return ""


def _identity_key(name: str, locators: tuple[str, ...]) -> str:
    if name:
        return f"name:{_identity_token(name)}"
    for locator in locators:
        if locator.startswith("@"):
            return f"handle:{locator.lower()}"
        domain_name = _domain_name(locator)
        if domain_name:
            return f"domain:{domain_name}"
    return ""


def _identity_token(value: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "", value.lower())


def _domain_name(locator: str) -> str:
    if locator.startswith("@"):
        return ""
    parsed = urlparse(locator if "://" in locator else f"https://{locator}")
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain:
        return ""
    return domain.split(".")[0]


def _clean_locator(locator: str) -> str:
    return locator.rstrip(".,;:!)")


def _has_solution_hint(
    text: str,
    locators: tuple[str, ...],
    name: str,
) -> bool:
    return bool(
        locators
        or name
        or _contains_any(text, SOLUTION_HINT_MARKERS)
    )


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(_contains_marker(text, marker) for marker in markers)


def _contains_marker(text: str, marker: str) -> bool:
    if marker == "бот":
        return bool(BOT_MARKER_RE.search(text))
    return marker in text


def _primary_subtype(subtypes: tuple[str, ...]) -> str:
    subtype_set = set(subtypes)
    for subtype in SOLUTION_SUBTYPE_ORDER:
        if subtype in subtype_set:
            return subtype
    return subtypes[0] if subtypes else "tool_mention"


def _sort_subtypes(subtypes: set[str]) -> tuple[str, ...]:
    return tuple(
        subtype for subtype in SOLUTION_SUBTYPE_ORDER if subtype in subtypes
    )


def _sort_trust_signals(signals: set[str]) -> tuple[str, ...]:
    order = (
        "price_discussion",
        "explicit_paid_subscription",
        "recommendation_from_participant",
        "repeated_independent_mention",
        "complaint_about_alternative",
    )
    return tuple(signal for signal in order if signal in signals)


def _merge_values(values: object) -> tuple[str, ...]:
    seen = set()
    merged = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return tuple(merged)


def _first_non_empty(values: object) -> str:
    for value in values:
        text = str(value)
        if text:
            return text
    return ""


def _first_known(values: object) -> str:
    for value in values:
        text = str(value)
        if text and text != "unknown":
            return text
    return "unknown"


def _has_repeated_independent_mentions(
    mentions: tuple[SolutionMention, ...],
) -> bool:
    strong_mentions = [
        mention
        for mention in mentions
        if "affiliate_or_spam" not in mention.flags
    ]
    if len(strong_mentions) < 2:
        return False
    return (
        len({_source_identity(mention) for mention in strong_mentions}) > 1
        and len({mention.normalized_text for mention in strong_mentions}) > 1
    )


def _source_identity(mention: SolutionMention) -> str:
    if mention.from_id:
        return f"from_id:{mention.from_id}"
    if mention.author:
        return f"author:{mention.author}"
    return f"chat:{mention.chat_id}"


def _trust_level(trust_payment_signals: tuple[str, ...]) -> str:
    if not trust_payment_signals:
        return "none"
    strong = {
        "price_discussion",
        "explicit_paid_subscription",
        "recommendation_from_participant",
    }
    if len(set(trust_payment_signals) & strong) >= 2:
        return "strong"
    if set(trust_payment_signals) & strong:
        return "medium"
    return "weak"


def _payment_status(
    *,
    trust_level: str,
    ad_signals: tuple[str, ...],
    has_ad_subtype: bool,
) -> str:
    if trust_level != "none":
        return "trust_signals_present"
    if has_ad_subtype or ad_signals:
        return "ad_only_unproven"
    return "mention_only_unproven"
