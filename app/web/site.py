from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


DATA_FILES = {
    "summary": "summary.json",
    "participants": "participants.json",
    "tools": "tools.json",
    "insights": "insights.json",
    "niches": "niches.json",
    "for_you": "for-you.json",
    "chat_meta": "chat_meta.json",
}


def write_static_site(site_payload: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    css_dir = output_dir / "css"
    data_dir.mkdir(exist_ok=True)
    css_dir.mkdir(exist_ok=True)

    for key, filename in DATA_FILES.items():
        (data_dir / filename).write_text(
            json.dumps(site_payload[key], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (css_dir / "style.css").write_text(_css(), encoding="utf-8")
    (output_dir / "favicon.svg").write_text(_favicon(), encoding="utf-8")

    pages = {
        "index.html": _index_page(site_payload),
        "people.html": _data_page(
            site_payload,
            active="people",
            title="Люди",
            subtitle="Карта участников без раскрытия реальных имен по умолчанию.",
            data_file="participants.json",
            renderer="renderPeople",
        ),
        "tools.html": _data_page(
            site_payload,
            active="tools",
            title="Тулзы И Решения",
            subtitle="Боты, сервисы, таблицы и рекламные сигналы из чата.",
            data_file="tools.json",
            renderer="renderTools",
        ),
        "insights.html": _data_page(
            site_payload,
            active="insights",
            title="Инсайты И Кейсы",
            subtitle="Сообщения, которые требуют ручного чтения и могут стать выводами.",
            data_file="insights.json",
            renderer="renderInsights",
        ),
        "niches.html": _data_page(
            site_payload,
            active="niches",
            title="Темы И Ниши",
            subtitle="Какие marketplace-темы чаще всего проявились в выборке.",
            data_file="niches.json",
            renderer="renderNiches",
        ),
        "for-you.html": _for_you_page(site_payload),
    }
    for filename, html in pages.items():
        (output_dir / filename).write_text(html, encoding="utf-8")


def _base(
    site_payload: dict[str, Any],
    *,
    active: str,
    title: str,
    body: str,
    script: str = "",
) -> str:
    project_name = site_payload["project"]["name"]
    meta = site_payload["chat_meta"]
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="ru">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(title)} — {escape(project_name)}</title>",
            '<link rel="icon" href="favicon.svg" type="image/svg+xml">',
            '<link rel="stylesheet" href="css/style.css">',
            "</head>",
            "<body>",
            '<header class="header">',
            '<div class="shell header-inner">',
            '<a class="brand" href="index.html">',
            f'<span class="brand-mark">{escape(_brand_letter(project_name))}</span>',
            f'<span class="brand-text">{escape(project_name)}<small>Chat KB</small></span>',
            "</a>",
            '<nav class="nav">',
            _nav_link("index", active, "index.html", "Дашборд"),
            _nav_link("for-you", active, "for-you.html", "Для тебя"),
            _nav_link("people", active, "people.html", "Люди"),
            _nav_link("tools", active, "tools.html", "Тулзы"),
            _nav_link("insights", active, "insights.html", "Инсайты"),
            _nav_link("niches", active, "niches.html", "Темы"),
            "</nav>",
            '<div class="stamp">',
            f'<strong>{escape(str(meta.get("last_date", "unknown")))}</strong>',
            f'<span>{escape(str(meta.get("last_time", "")))}</span>',
            "</div>",
            "</div>",
            "</header>",
            body,
            '<footer class="footer"><div class="shell">Локальный отчет. Raw данные остаются в приватных папках.</div></footer>',
            script,
            "</body>",
            "</html>",
        ]
    )


def _index_page(site_payload: dict[str, Any]) -> str:
    project_name = site_payload["project"]["name"]
    project_summary = site_payload["project"]["summary"]
    counts = site_payload["summary"]["counts"]
    body = (
        '<main class="page">'
        '<section class="hero">'
        '<div class="shell hero-grid">'
        '<div>'
        '<p class="eyebrow">Локальная выжимка Telegram-чата</p>'
        f'<h1>Что чат говорит про <span>{escape(project_name)}</span></h1>'
        f'<p class="lead">{escape(project_summary)}</p>'
        '<div class="hero-actions">'
        '<a class="button primary" href="for-you.html">Открыть “Для тебя”</a>'
        '<a class="button" href="tools.html">Смотреть решения</a>'
        "</div>"
        "</div>"
        '<div class="hero-panel">'
        f'<div class="big-number">{escape(str(counts.get("messages", 0)))}</div>'
        '<div class="muted">сообщений обработано</div>'
        "</div>"
        "</div>"
        "</section>"
        '<section class="section"><div class="shell">'
        '<div class="metrics">'
        + _metric("Чаты", counts.get("chats", 0))
        + _metric("Сообщения", counts.get("messages", 0))
        + _metric("Метки", counts.get("labels", 0))
        + _metric("Без метки", counts.get("unclassified", 0))
        + _metric("Люди", len(site_payload["participants"]))
        + _metric("Тулзы", len(site_payload["tools"]))
        + _metric("Инсайты", len(site_payload["insights"]))
        + _metric("Темы", len(site_payload["niches"]))
        + "</div>"
        "</div></section>"
        '<section class="section"><div class="shell">'
        '<div class="section-head"><p class="eyebrow">Разделы</p><h2>Куда смотреть</h2></div>'
        '<div class="grid cards">'
        + _link_card("Для тебя", "Персональная подборка действий, гипотез и проверок.", "for-you.html")
        + _link_card("Люди", "Участники и активность через приватность-безопасные aliases.", "people.html")
        + _link_card("Тулзы", "Готовые решения, реклама и упоминания инструментов.", "tools.html")
        + _link_card("Инсайты", "Кейсы, наблюдения и сообщения для ручной проверки.", "insights.html")
        + _link_card("Темы", "Какие marketplace-темы чаще всего проявились.", "niches.html")
        + "</div>"
        "</div></section>"
        "</main>"
    )
    return _base(site_payload, active="index", title="Дашборд", body=body)


def _data_page(
    site_payload: dict[str, Any],
    *,
    active: str,
    title: str,
    subtitle: str,
    data_file: str,
    renderer: str,
) -> str:
    body = (
        '<main class="page">'
        '<section class="page-title"><div class="shell">'
        f"<h1>{escape(title)}</h1>"
        f'<p>{escape(subtitle)}</p>'
        '<div class="toolbar"><input id="search" type="search" placeholder="Фильтр по странице"><span id="counter"></span></div>'
        "</div></section>"
        '<section class="section"><div class="shell"><div id="cards" class="grid cards"></div></div></section>'
        "</main>"
    )
    script = (
        "<script>"
        f"const DATA_FILE='data/{data_file}';"
        f"const RENDERER={renderer};"
        + _common_js()
        + "</script>"
    )
    return _base(site_payload, active=active, title=title, body=body, script=script)


def _for_you_page(site_payload: dict[str, Any]) -> str:
    body = (
        '<main class="page">'
        '<section class="hero compact"><div class="shell">'
        '<p class="eyebrow">Персональная подборка</p>'
        '<h1>Что применить дальше</h1>'
        '<p class="lead">Этот раздел собирает действия, людей-aliases, паттерны и открытые вопросы из анализа чата.</p>'
        "</div></section>"
        '<section class="section"><div class="shell stack">'
        '<div><h2>Фокус Проекта</h2><div id="fit" class="grid cards"></div></div>'
        '<div><h2>Совпадения С Фокусом</h2><div id="matches" class="grid cards"></div></div>'
        '<div><h2>Следующая Проверка</h2><div id="review" class="grid cards"></div></div>'
        '<div><h2>Предупреждения Профиля</h2><div id="warnings" class="grid cards"></div></div>'
        '<div><h2>Сделать Сейчас</h2><div id="now" class="grid cards"></div></div>'
        '<div><h2>Кого Проверить</h2><div id="people" class="grid cards"></div></div>'
        '<div><h2>Что Забрать В Проект</h2><div id="apply" class="grid cards"></div></div>'
        '<div><h2>Открытые Вопросы</h2><div id="issues" class="grid cards"></div></div>'
        '<div><h2>Принципы</h2><div id="principles" class="principles"></div></div>'
        "</div></section>"
        "</main>"
    )
    script = "<script>" + _for_you_js() + "</script>"
    return _base(site_payload, active="for-you", title="Для тебя", body=body, script=script)


def _common_js() -> str:
    return r"""
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const card = (title, body, meta='') => `<article class="card"><h3>${esc(title)}</h3>${meta ? `<p class="meta">${esc(meta)}</p>` : ''}<p>${body}</p></article>`;
const renderPeople = item => card(item.name, esc(item.summary), `${item.message_count} сообщений · ${item.top_categories || 'no labels'}`);
const renderTools = item => card(item.name, esc(item.description), `${item.solution_type} · ${item.payment_status}`);
const renderInsights = item => card(item.title, esc(item.summary), `${item.category} · ${item.message_id}`);
const renderNiches = item => card(item.title, esc(item.summary), `${item.message_count} сообщений · ${item.evidence_message_ids || 'no evidence'}`);

let allItems = [];
fetch(DATA_FILE).then(r => r.json()).then(data => {
  allItems = Array.isArray(data) ? data : [];
  document.getElementById('search').addEventListener('input', render);
  render();
});
function render() {
  const q = document.getElementById('search').value.toLowerCase().trim();
  const filtered = allItems.filter(item => JSON.stringify(item).toLowerCase().includes(q));
  document.getElementById('counter').textContent = `${filtered.length} из ${allItems.length}`;
  document.getElementById('cards').innerHTML = filtered.map(RENDERER).join('') || '<p class="empty">Ничего не найдено.</p>';
}
"""


def _for_you_js() -> str:
    return r"""
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const list = items => `<ul>${(items || []).map(item => `<li>${esc(item)}</li>`).join('')}</ul>`;
const card = (title, body, meta='') => `<article class="card"><h3>${esc(title)}</h3>${meta ? `<p class="meta">${esc(meta)}</p>` : ''}${body}</article>`;
const inline = items => (items || []).length ? esc((items || []).join(', ')) : 'none';
fetch('data/for-you.json').then(r => r.json()).then(data => {
  document.getElementById('fit').innerHTML = (data.project_fit || []).map(item =>
    card(item.title, list(item.items) + `<p>${esc(item.why || '')}</p>`)
  ).join('') || '<p class="empty">Project profile не задан.</p>';
  document.getElementById('matches').innerHTML = (data.profile_matches || []).map(item =>
    card(item.title, `<p>${esc(item.reason || '')}</p><p><strong>Темы:</strong> ${inline(item.matched_themes)}</p><p><strong>Evidence:</strong> ${inline(item.evidence_aliases)}</p>`, `${item.priority || 'P1'} · ${item.type || 'match'}`)
  ).join('') || '<p class="empty">Нет совпадений с focus_themes.</p>';
  document.getElementById('review').innerHTML = (data.recommended_next_review || []).map(item =>
    card(item.title, `<p>${esc(item.action || '')}</p><p>${esc(item.reason || '')}</p><p><strong>Evidence:</strong> ${inline(item.evidence_aliases)}</p>`, item.priority || 'P1')
  ).join('') || '<p class="empty">Нет следующих действий.</p>';
  document.getElementById('warnings').innerHTML = (data.profile_warnings || []).map(item =>
    card(item.code, `<p>${esc(item.message || '')}</p><p><strong>Темы:</strong> ${inline(item.themes)}</p><p><strong>Evidence:</strong> ${inline(item.evidence_aliases)}</p>`, item.priority || 'P1')
  ).join('') || '<p class="empty">Нет предупреждений профиля.</p>';
  document.getElementById('now').innerHTML = (data.now || []).map(item =>
    card(item.title, list(item.actions) + `<p>${esc(item.why || '')}</p>`, item.priority || 'P1')
  ).join('') || '<p class="empty">Нет действий.</p>';
  document.getElementById('people').innerHTML = (data.people_to_contact || []).map(item =>
    card(item.name, `<p>${esc(item.why || '')}</p><p><strong>Что спросить:</strong> ${esc(item.ask || '')}</p>`, item.project || '')
  ).join('') || '<p class="empty">Нет людей для проверки.</p>';
  document.getElementById('apply').innerHTML = (data.to_apply || []).map(item =>
    card(item.from, `<p>${esc(item.what || '')}</p><p><strong>Как применить:</strong> ${esc(item.applicability || '')}</p>`, `rating ${item.rating || 3}/5`)
  ).join('') || '<p class="empty">Нет паттернов.</p>';
  document.getElementById('issues').innerHTML = (data.open_issues_to_solve || []).map(item =>
    card(item.issue, `<p>${esc(item.your_status || '')}</p>${list(item.ideas_from_chat)}`)
  ).join('') || '<p class="empty">Нет открытых вопросов.</p>';
  document.getElementById('principles').innerHTML = list(data.principles_to_remember || []);
});
"""


def _css() -> str:
    return """
:root {
  --bg: #fffdf8;
  --fg: #111111;
  --muted: #6d6a62;
  --line: #e8dfcf;
  --card: #ffffff;
  --accent: #f2b705;
  --accent-dark: #7a5600;
  --soft: #fbf1d1;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font-family: Arial, Helvetica, sans-serif; line-height: 1.45; }
.shell { width: min(1160px, calc(100% - 32px)); margin: 0 auto; }
.header { position: sticky; top: 0; z-index: 10; background: rgba(255,253,248,.94); border-bottom: 1px solid var(--line); backdrop-filter: blur(12px); }
.header-inner { display: flex; align-items: center; gap: 20px; min-height: 68px; }
.brand { display: inline-flex; align-items: center; gap: 10px; color: inherit; text-decoration: none; min-width: 190px; }
.brand-mark { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 8px; background: var(--accent); font-weight: 900; }
.brand-text { display: grid; font-weight: 800; line-height: 1.05; }
.brand-text small { color: var(--muted); font-size: 12px; font-weight: 600; }
.nav { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.nav a { color: var(--muted); text-decoration: none; padding: 8px 10px; border-radius: 8px; font-size: 14px; font-weight: 700; }
.nav a.active, .nav a:hover { background: var(--soft); color: var(--fg); }
.stamp { display: grid; gap: 1px; color: var(--muted); font-size: 12px; text-align: right; }
.stamp strong { color: var(--fg); }
.page { padding-bottom: 44px; }
.hero { padding: 64px 0 42px; border-bottom: 1px solid var(--line); }
.hero.compact { padding: 44px 0 30px; }
.hero-grid { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 28px; align-items: end; }
.eyebrow { margin: 0 0 10px; color: var(--accent-dark); font-size: 13px; font-weight: 900; text-transform: uppercase; }
h1 { margin: 0; font-size: 54px; line-height: .98; letter-spacing: 0; }
h1 span { background: var(--accent); padding: 0 8px; }
.lead { max-width: 760px; color: var(--muted); font-size: 17px; margin: 18px 0 0; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
.button { display: inline-flex; align-items: center; min-height: 42px; padding: 0 14px; border: 1px solid var(--line); border-radius: 8px; color: var(--fg); text-decoration: none; font-weight: 800; background: var(--card); }
.button.primary { background: var(--fg); color: var(--bg); border-color: var(--fg); }
.hero-panel, .metric, .card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 18px; }
.big-number { font-size: 54px; font-weight: 900; }
.muted, .meta { color: var(--muted); }
.section { padding: 34px 0; }
.section h2, .page-title h1 { margin: 0 0 14px; font-size: 32px; letter-spacing: 0; }
.section-head { margin-bottom: 16px; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.metric strong { display: block; font-size: 30px; margin-top: 6px; }
.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.cards .card h3 { margin: 0 0 8px; font-size: 18px; }
.cards .card p { margin: 0 0 10px; color: var(--muted); }
.cards .card p:last-child { margin-bottom: 0; }
.page-title { padding: 40px 0 16px; border-bottom: 1px solid var(--line); }
.page-title p { color: var(--muted); max-width: 720px; margin: 0 0 18px; }
.toolbar { display: flex; gap: 12px; align-items: center; }
input[type=search] { width: min(520px, 100%); height: 42px; border: 1px solid var(--line); border-radius: 8px; padding: 0 12px; font: inherit; background: var(--card); }
.stack { display: grid; gap: 34px; }
ul { margin: 0; padding-left: 18px; }
li + li { margin-top: 6px; }
.principles { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 18px; }
.empty { color: var(--muted); }
.footer { border-top: 1px solid var(--line); color: var(--muted); padding: 20px 0; font-size: 13px; }
@media (max-width: 860px) {
  .header-inner { align-items: flex-start; flex-direction: column; padding: 12px 0; }
  .stamp { text-align: left; }
  .hero-grid, .metrics, .grid { grid-template-columns: 1fr; }
  h1 { font-size: 38px; }
}
"""


def _favicon() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#f2b705"/>'
        '<path d="M16 20h32v6H16zm0 12h24v6H16zm0 12h30v6H16z" fill="#111"/>'
        "</svg>"
    )


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'


def _link_card(title: str, body: str, href: str) -> str:
    return (
        f'<a class="card" href="{escape(href)}">'
        f"<h3>{escape(title)}</h3>"
        f"<p>{escape(body)}</p>"
        "</a>"
    )


def _nav_link(key: str, active: str, href: str, label: str) -> str:
    klass = ' class="active"' if key == active else ""
    return f'<a{klass} href="{escape(href)}">{escape(label)}</a>'


def _brand_letter(project_name: str) -> str:
    stripped = project_name.strip()
    return stripped[:1].upper() if stripped else "M"
