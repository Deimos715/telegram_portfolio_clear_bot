import os
import time
import re
import html
from datetime import datetime
from typing import Dict, Any, List

from db_handler.db_funk import (
    get_user_count,
    get_cases_count,
    get_case_media_count,
    get_events_total,
    get_top_menu_clicks,
    get_top_cases,
    get_funnel,
    get_stuck_points,
    get_recent_users,
)


def _build_table_rows(rows: List[List[str]], colspan: int) -> str:
    if not rows:
        return f"<tr><td colspan=\"{colspan}\">нет данных</td></tr>"
    return "".join(
        f"<tr>{''.join(f'<td>{cell}</td>' for cell in row)}</tr>" for row in rows
    )


async def build_statistics_context() -> Dict[str, Any]:
    users_total = await get_user_count()
    cases_total = await get_cases_count()
    cases_published = await get_cases_count(status="published")
    cases_draft = await get_cases_count(status="draft")
    cases_archived = await get_cases_count(status="archived")
    media_total = await get_case_media_count()

    events_total = await get_events_total(days=30)
    top_menu = await get_top_menu_clicks(days=30, limit=15)
    top_cases = await get_top_cases(days=30, limit=10)
    funnel = await get_funnel(days=30)
    stuck = await get_stuck_points(days=30, limit=10)
    recent_users = await get_recent_users(limit=100)

    top_menu_rows: List[List[str]] = []
    for item in top_menu:
        label = item.get("event_value") or item.get("event_context") or "(без названия)"
        label = html.escape(str(label))
        cnt = html.escape(str(item.get("cnt", 0)))
        top_menu_rows.append([label, cnt])

    top_cases_rows: List[List[str]] = []
    for item in top_cases:
        case_id = item.get("case_id")
        title = item.get("title") or f"Кейс #{case_id}"
        title = html.escape(str(title))
        cnt = html.escape(str(item.get("cnt", 0)))
        top_cases_rows.append([title, cnt])

    funnel_map = {row.get("event_type"): int(row.get("users", 0)) for row in funnel}
    funnel_steps = [
        ("start", "Старт"),
        ("cases_open", "Открыли кейсы"),
        ("case_view", "Открыли кейс"),
        ("contact_open", "Открыли контакты"),
    ]
    funnel_rows: List[List[str]] = []
    for key, label in funnel_steps:
        users = funnel_map.get(key, 0)
        funnel_rows.append([html.escape(label), html.escape(str(users))])

    stuck_rows: List[List[str]] = []
    for item in stuck:
        label = html.escape(str(item.get("label", "")))
        users = html.escape(str(item.get("users", 0)))
        stuck_rows.append([label, users])

    users_rows: List[List[str]] = []
    for item in recent_users:
        full_name = item.get("full_name") or "—"
        username = item.get("username") or ""
        last_activity = item.get("last_activity")
        if isinstance(last_activity, datetime):
            last_activity_str = last_activity.strftime("%Y-%m-%d %H:%M")
        else:
            last_activity_str = str(last_activity) if last_activity else "—"

        full_name = html.escape(str(full_name))
        username_text = f"@{username}" if username else "—"
        username_text = html.escape(username_text)
        last_activity_str = html.escape(last_activity_str)
        if username:
            link = f"<a href=\"https://t.me/{html.escape(username)}\">@{html.escape(username)}</a>"
        else:
            link = "—"
        users_rows.append([full_name, username_text, last_activity_str, link])

    context = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "users_total": users_total,
        "cases_total": cases_total,
        "cases_published": cases_published,
        "cases_draft": cases_draft,
        "cases_archived": cases_archived,
        "media_total": media_total,
        "events_total": events_total,
        "top_buttons_rows": _build_table_rows(top_menu_rows, colspan=2),
        "top_cases_rows": _build_table_rows(top_cases_rows, colspan=2),
        "funnel_rows": _build_table_rows(funnel_rows, colspan=2),
        "stuck_rows": _build_table_rows(stuck_rows, colspan=2),
        "users_rows": _build_table_rows(users_rows, colspan=4),
    }
    return context


async def render_statistics_html(context: Dict[str, Any], template_path: str) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    for key, value in context.items():
        template = template.replace(f"{{{{{key}}}}}", str(value))

    template = re.sub(r"\{\{[a-zA-Z0-9_]+\}\}", "", template)
    return template


async def generate_statistics_report_file(template_path: str) -> str:
    context = await build_statistics_context()
    html_content = await render_statistics_html(context, template_path)

    output_dir = os.path.join("src", "html", "out")
    os.makedirs(output_dir, exist_ok=True)
    ts = int(time.time())
    output_path = os.path.join(output_dir, f"statistics_{ts}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path
