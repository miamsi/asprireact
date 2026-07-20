"""Timezone-aware date helpers so the assistant can reason about 'today', 'tomorrow', etc."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from dateutil import parser as dateparser


def get_timezone() -> ZoneInfo:
    # st.secrets.get("app", {}) can return None instead of the given default when the [app]
    # section is missing from secrets.toml — the `or {}` below guards against that.
    app_config = st.secrets.get("app", {}) or {}
    tz_name = app_config.get("timezone", "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def now_local() -> datetime:
    return datetime.now(get_timezone())


def now_label() -> str:
    """Human string used inside the LLM system prompt, e.g. 'Tuesday, 2026-07-07 14:32 (Asia/Jakarta)'."""
    n = now_local()
    return n.strftime("%A, %Y-%m-%d %H:%M") + f" ({n.tzname()})"


def parse_due_date(text: str | None) -> str | None:
    """
    Parse a date/time string (ideally already an absolute ISO date/time produced by the LLM,
    e.g. '2026-07-08' or '2026-07-08T09:00') into a timezone-aware ISO 8601 string for storage.
    Returns None if it can't be parsed.
    """
    if not text or not text.strip():
        return None
    tz = get_timezone()
    try:
        dt = dateparser.parse(text, default=now_local())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.isoformat()
    except (ValueError, OverflowError):
        return None


def humanize_due(due_iso: str | None) -> str | None:
    """Turn a stored ISO due_date back into a friendly label like 'Today 14:00', 'Tomorrow', 'Overdue (Jul 3)'."""
    if not due_iso:
        return None
    try:
        due = dateparser.parse(due_iso)
        if due.tzinfo is None:
            due = due.replace(tzinfo=get_timezone())
    except (ValueError, OverflowError):
        return due_iso

    now = now_local()
    due_local = due.astimezone(get_timezone())
    today = now.date()
    due_day = due_local.date()
    has_time = not (due_local.hour == 0 and due_local.minute == 0)
    time_part = due_local.strftime(" %H:%M") if has_time else ""

    if due_day < today:
        return f"Overdue ({due_local.strftime('%b %d')}{time_part})"
    if due_day == today:
        return f"Today{time_part}"
    if due_day == today + timedelta(days=1):
        return f"Tomorrow{time_part}"
    if due_day <= today + timedelta(days=6):
        return due_local.strftime("%A") + time_part
    return due_local.strftime("%b %d") + time_part
