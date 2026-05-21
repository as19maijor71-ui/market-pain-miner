from __future__ import annotations

from html import escape
from typing import Any


def render_html_report(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    active_classifier = payload.get("active_classifier")
    quality_gaps = list(payload.get("quality_gaps", []))
    categories = list(payload.get("category_distribution", []))
    frequencies = list(payload.get("deduplicated_frequencies", []))
    clusters = list(payload.get("top_clusters", []))
    solutions = list(payload.get("solutions", []))
    opportunities = list(payload.get("opportunities", []))
    review = dict(payload.get("review_candidates", {}))

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="ru">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Market Pain Miner Report</title>",
            f"<style>{_css()}</style>",
            "</head>",
            "<body>",
            '<main class="page">',
            _hero(counts, quality_gaps),
            _section(
                "Сводка",
                _metric_grid(
                    [
                        ("Чаты", counts.get("chats", 0)),
                        ("Сообщения", counts.get("messages", 0)),
                        ("Метки", counts.get("labels", 0)),
                        ("Без метки", counts.get("unclassified", 0)),
                    ]
                )
                + _classifier_block(active_classifier),
            ),
            _section(
                "Что Нашли",
                _bar_list(categories, "category", "count", "Сообщений")
                + _frequency_table(frequencies),
            ),
            _section(
                "Кластеры Болей И Вопросов",
                _clusters_table(clusters),
            ),
            _section(
                "Решения И Конкуренты",
                _solutions_table(solutions),
            ),
            _section(
                "Гипотезы",
                _opportunities_table(opportunities),
            ),
            _section(
                "Ручная Проверка",
                _review_block(review),
            ),
            _section(
                "Пробелы Качества",
                _list_block(quality_gaps, empty="Пробелов не найдено."),
            ),
            _privacy_note(),
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f5f7f4;
  --text: #1f2522;
  --muted: #647067;
  --line: #d9e0d8;
  --panel: #ffffff;
  --accent: #176b5b;
  --accent-2: #9a5b12;
  --accent-soft: #dfeee9;
  --warn-soft: #f5ead9;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Arial, Helvetica, sans-serif;
  line-height: 1.45;
}
.page { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 44px; }
.hero {
  padding: 28px 0 20px;
  border-bottom: 1px solid var(--line);
}
.eyebrow { margin: 0 0 8px; color: var(--accent); font-size: 13px; font-weight: 700; text-transform: uppercase; }
h1 { margin: 0; font-size: 34px; line-height: 1.12; letter-spacing: 0; }
.lead { max-width: 760px; margin: 12px 0 0; color: var(--muted); font-size: 16px; }
.section { padding: 26px 0; border-bottom: 1px solid var(--line); }
.section h2 { margin: 0 0 14px; font-size: 22px; letter-spacing: 0; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.metric, .note {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.metric .label { color: var(--muted); font-size: 13px; }
.metric .value { margin-top: 6px; font-size: 26px; font-weight: 700; }
.note { margin-top: 12px; color: var(--muted); }
.bars { display: grid; gap: 8px; margin-bottom: 18px; }
.bar-row { display: grid; grid-template-columns: minmax(140px, 220px) 1fr 64px; gap: 10px; align-items: center; }
.bar-track { height: 12px; background: #e7ece5; border-radius: 999px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--accent); }
table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 14px; }
th { background: #eef3ee; color: #33403a; font-weight: 700; }
tr:last-child td { border-bottom: 0; }
.tag { display: inline-block; padding: 2px 7px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 12px; font-weight: 700; }
.warn { background: var(--warn-soft); color: var(--accent-2); }
.empty { color: var(--muted); margin: 0; }
ul { margin: 0; padding-left: 18px; }
li + li { margin-top: 6px; }
.privacy { padding: 18px 0 0; color: var(--muted); font-size: 13px; }
@media (max-width: 760px) {
  .page { width: min(100% - 20px, 1180px); padding-top: 16px; }
  h1 { font-size: 28px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .bar-row { grid-template-columns: 1fr; gap: 4px; }
  table { display: block; overflow-x: auto; }
}
"""


def _hero(counts: dict[str, Any], quality_gaps: list[Any]) -> str:
    messages = _to_int(counts.get("messages", 0))
    gap_text = (
        f"Есть {len(quality_gaps)} пункт(ов) для ручной проверки."
        if quality_gaps
        else "Критичных пробелов качества в summary не найдено."
    )
    return (
        '<section class="hero">'
        '<p class="eyebrow">Market Pain Miner</p>'
        "<h1>Отчет по Telegram-чату WB/Ozon</h1>"
        f'<p class="lead">Проанализировано {messages} сообщений. '
        "Ниже показано, какие сигналы найдены, какие evidence IDs их поддерживают "
        f"и какие продуктовые гипотезы появились. {escape(gap_text)}</p>"
        "</section>"
    )


def _section(title: str, body: str) -> str:
    return f'<section class="section"><h2>{escape(title)}</h2>{body}</section>'


def _metric_grid(items: list[tuple[str, Any]]) -> str:
    cards = []
    for label, value in items:
        cards.append(
            '<div class="metric">'
            f'<div class="label">{escape(label)}</div>'
            f'<div class="value">{escape(str(value))}</div>'
            "</div>"
        )
    return '<div class="metrics">' + "".join(cards) + "</div>"


def _classifier_block(active_classifier: Any) -> str:
    if not active_classifier:
        return '<div class="note">Активный классификатор: нет.</div>'
    text = (
        f"{active_classifier.get('source')}/"
        f"{active_classifier.get('classifier_name')} "
        f"{active_classifier.get('classifier_version')} "
        f"run={active_classifier.get('run_id')}"
    )
    return f'<div class="note">Активный классификатор: {escape(text)}</div>'


def _bar_list(rows: list[dict[str, Any]], label_key: str, value_key: str, title: str) -> str:
    if not rows:
        return '<p class="empty">Категории не найдены.</p>'
    max_value = max(_to_int(row.get(value_key, 0)) for row in rows) or 1
    items = []
    for row in rows:
        label = str(row.get(label_key, "unknown"))
        value = _to_int(row.get(value_key, 0))
        width = max(2, int(value / max_value * 100))
        items.append(
            '<div class="bar-row">'
            f"<strong>{escape(label)}</strong>"
            '<div class="bar-track">'
            f'<div class="bar-fill" style="width:{width}%"></div>'
            "</div>"
            f"<span>{value}</span>"
            "</div>"
        )
    return f'<h3>{escape(title)}</h3><div class="bars">{"".join(items)}</div>'


def _frequency_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Частоты не найдены.</p>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(row.get('category', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('raw_count', 0)))}</td>"
            f"<td>{escape(str(row.get('unique_count', 0)))}</td>"
            f"<td>{escape(str(row.get('duplicate_count', 0)))}</td>"
            f"<td>{escape(str(row.get('weaker_evidence_count', 0)))}</td>"
            "</tr>"
        )
    return (
        "<h3>Дедуплицированные Частоты</h3>"
        "<table><thead><tr>"
        "<th>Категория</th><th>Raw</th><th>Unique</th><th>Duplicates</th><th>Weak evidence</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _clusters_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Кластеры не найдены.</p>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(row.get('cluster_id', 'unknown')))}</td>"
            f"<td>{_status(row.get('support_status'))}</td>"
            f"<td>{escape(str(row.get('topic', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('problem_marker', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('unique_count', 0)))}</td>"
            f"<td>{escape(str(row.get('evidence_message_ids', 'none')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Cluster</th><th>Status</th><th>Topic</th><th>Marker</th><th>Unique</th><th>Evidence IDs</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _solutions_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Решения и конкуренты не найдены.</p>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(row.get('solution_id', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('primary_subtype', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('solution_type', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('trust_level', 'none')))}</td>"
            f"<td>{escape(str(row.get('payment_status', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('locators', 'none')))}</td>"
            f"<td>{escape(str(row.get('source_message_ids', 'none')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>ID</th><th>Subtype</th><th>Type</th><th>Trust</th><th>Payment</th><th>Locators</th><th>Evidence IDs</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _opportunities_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Гипотезы не найдены.</p>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(row.get('opportunity_id', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('cluster_id', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('score', 0)))}</td>"
            f"<td>{escape(str(row.get('verdict', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('first_mvp', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('payment_reason', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('evidence_message_ids', 'none')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Hypothesis</th><th>Cluster</th><th>Score</th><th>Verdict</th><th>MVP</th><th>Why pay</th><th>Evidence IDs</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _review_block(review: dict[str, Any]) -> str:
    counts = _metric_grid(
        [
            ("Labels", review.get("low_confidence_or_disputed_labels", 0)),
            ("Weak clusters", review.get("weak_signal_clusters", 0)),
            ("Noise cases", review.get("disputed_noise_cases", 0)),
            ("Cards", review.get("opportunity_cards_needing_review", 0)),
        ]
    )
    low_confidence = list(review.get("low_confidence", []))
    if not low_confidence:
        return counts + '<p class="empty">Очередь ручной проверки пуста.</p>'

    rows = []
    for item in low_confidence:
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('message_id', 'unknown')))}</td>"
            f"<td>{escape(str(item.get('category', 'unknown')))}</td>"
            f"<td>{escape(str(item.get('confidence', 'unknown')))}</td>"
            f"<td>{escape(str(item.get('reason', 'review')))}</td>"
            "</tr>"
        )
    return (
        counts
        + "<h3>Первые Кандидаты</h3>"
        + "<table><thead><tr><th>Message ID</th><th>Category</th><th>Confidence</th><th>Reason</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _list_block(items: list[Any], *, empty: str) -> str:
    if not items:
        return f'<p class="empty">{escape(empty)}</p>'
    return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in items) + "</ul>"


def _privacy_note() -> str:
    return (
        '<p class="privacy">'
        "Отчет создан в privacy-safe режиме: используются aliases, агрегаты и evidence IDs. "
        "Raw names, Telegram handles, URLs, user IDs и приватные цитаты не выводятся."
        "</p>"
    )


def _status(value: Any) -> str:
    text = str(value or "unknown")
    klass = "tag warn" if text == "weak_signal" else "tag"
    return f'<span class="{klass}">{escape(text)}</span>'


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
