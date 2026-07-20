"""Supabase auth + todos data access layer."""
import os
from datetime import timedelta, datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
from time_utils import now_local, parse_due_date

# Load local system environment variables
load_dotenv()

def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_ANON_KEY environment variables.")
    return create_client(url, key)

# ---------- Auth ----------

def sign_up(email: str, password: str):
    sb = get_supabase_client()
    return sb.auth.sign_up({"email": email, "password": password})


def sign_in(email: str, password: str):
    sb = get_supabase_client()
    return sb.auth.sign_in_with_password({"email": email, "password": password})


def sign_out():
    sb = get_supabase_client()
    try:
        sb.auth.sign_out()
    except Exception:
        pass


# ---------- Todos ----------

VALID_CATEGORIES = {"work", "personal", "errand", "health", "finance", "shopping", "study", "other"}
VALID_PRIORITIES = {"low", "medium", "high"}


def add_todo(
    user_id: str,
    task: str,
    embedding: list | None = None,
    due_at: str | None = None,
    category: str | None = None,
    priority: str | None = None,
) -> dict:
    sb = get_supabase_client()
    row = {
        "user_id": user_id,
        "task": task,
        "is_done": False,
        "category": category if category in VALID_CATEGORIES else "other",
        "priority": priority if priority in VALID_PRIORITIES else "medium",
    }
    if embedding is not None:
        row["embedding"] = embedding
    parsed_due = parse_due_date(due_at) if due_at else None
    if parsed_due:
        row["due_at"] = parsed_due
    res = sb.table("todos").insert(row).execute()
    return res.data[0] if res.data else {}


def _fetch_all(user_id: str) -> list[dict]:
    sb = get_supabase_client()
    res = (
        sb.table("todos")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )
    todos = res.data or []
    todos.sort(key=lambda t: (t["due_at"] is None, t["due_at"] or ""))
    return todos


def list_todos(user_id: str, filter: str = "open") -> list[dict]:
    todos = _fetch_all(user_id)
    if filter == "all":
        return todos
    if filter == "done":
        return [t for t in todos if t["is_done"]]
    if filter == "open":
        return [t for t in todos if not t["is_done"]]

    now = now_local()
    today = now.date()

    def due_date(t):
        if not t.get("due_at"):
            return None
        try:
            from dateutil import parser as dateparser
            d = dateparser.parse(t["due_at"])
            return d.astimezone(now.tzinfo).date() if d.tzinfo else d.date()
        except Exception:
            return None

    if filter == "overdue":
        return [t for t in todos if not t["is_done"] and (d := due_date(t)) and d < today]
    if filter == "today":
        return [t for t in todos if not t["is_done"] and due_date(t) == today]
    if filter == "upcoming":
        cutoff = today + timedelta(days=7)
        return [
            t for t in todos
            if not t["is_done"] and (d := due_date(t)) and today <= d <= cutoff
        ]
    return [t for t in todos if not t["is_done"]]


def find_matching_todos(user_id: str, text_snippet: str, status: str = "open") -> list[dict]:
    todos = _fetch_all(user_id)
    if status == "open":
        todos = [t for t in todos if not t["is_done"]]
    elif status == "done":
        todos = [t for t in todos if t["is_done"]]
    snippet = text_snippet.lower().strip()
    return [t for t in todos if snippet in t["task"].lower()]


def find_todo_by_text(user_id: str, text_snippet: str) -> dict | None:
    matches = find_matching_todos(user_id, text_snippet)
    return matches[0] if matches else None


def complete_todo(todo_id: str) -> dict:
    sb = get_supabase_client()
    res = (
        sb.table("todos")
        .update({"is_done": True, "completed_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", todo_id)
        .execute()
    )
    return res.data[0] if res.data else {}


def reopen_todo(todo_id: str) -> dict:
    sb = get_supabase_client()
    res = (
        sb.table("todos")
        .update({"is_done": False, "completed_at": None})
        .eq("id", todo_id)
        .execute()
    )
    return res.data[0] if res.data else {}


def delete_todo(todo_id: str) -> None:
    sb = get_supabase_client()
    sb.table("todos").delete().eq("id", todo_id).execute()


def reschedule_todo(todo_id: str, due_at: str | None) -> dict:
    sb = get_supabase_client()
    parsed = parse_due_date(due_at) if due_at else None
    res = sb.table("todos").update({"due_at": parsed}).eq("id", todo_id).execute()
    return res.data[0] if res.data else {}


def reclassify_todo(todo_id: str, category: str | None = None, priority: str | None = None) -> dict:
    sb = get_supabase_client()
    updates = {}
    if category in VALID_CATEGORIES:
        updates["category"] = category
    if priority in VALID_PRIORITIES:
        updates["priority"] = priority
    if not updates:
        return {}
    res = sb.table("todos").update(updates).eq("id", todo_id).execute()
    return res.data[0] if res.data else {}


def semantic_search(user_id: str, query_embedding: list, match_count: int = 5) -> list[dict]:
    sb = get_supabase_client()
    res = sb.rpc(
        "match_todos",
        {
            "query_embedding": query_embedding,
            "match_user_id": user_id,
            "match_count": match_count,
        },
    ).execute()
    return res.data or []
