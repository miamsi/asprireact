"""
Notes connector: freeform notes, separate from the todos domain.

This exists mainly to prove the connector architecture actually generalizes — it's a second,
independent capability that plugs in without touching agent.py, db.py, or the todos connector.
Add your own connector the same way: own tool schemas, own handle(), own data access.
"""
import db
from jina_client import get_embedding
from .base import Connector

SYSTEM_PROMPT = """
NOTES — RULES:
- Use add_note for anything the user wants to jot down or remember that ISN'T an actionable task
  with a deadline (e.g. "note that the wifi password is X", "remember that Sarah prefers email").
  If it has a clear action + deadline, that's a todo instead — use the todos tools for that.
- Use search_notes for meaning-based lookups ("what did I write about the wifi?").
- Keep replies short and confirm what was saved in your own words.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": "Save a freeform note for later reference (not a task with a deadline).",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string", "description": "The note text to save."}},
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "List the user's saved notes, most recent first.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Semantically search the user's notes for ones related to a topic or meaning.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What the user is looking for."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Delete a note, based on a description of its content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_query": {"type": "string", "description": "Words describing which note to delete."}
                },
                "required": ["note_query"],
            },
        },
    },
]


def _add_note(user_id: str, content: str, embedding: list | None) -> dict:
    sb = db.get_supabase_client()
    row = {"user_id": user_id, "content": content}
    if embedding is not None:
        row["embedding"] = embedding
    res = sb.table("notes").insert(row).execute()
    return res.data[0] if res.data else {}


def _list_notes(user_id: str) -> list[dict]:
    sb = db.get_supabase_client()
    res = (
        sb.table("notes").select("*").eq("user_id", user_id)
        .order("created_at", desc=True).execute()
    )
    return res.data or []


def _find_notes(user_id: str, snippet: str) -> list[dict]:
    snippet_l = snippet.lower().strip()
    return [n for n in _list_notes(user_id) if snippet_l in n["content"].lower()]


def _delete_note(note_id: str) -> None:
    sb = db.get_supabase_client()
    sb.table("notes").delete().eq("id", note_id).execute()


def _semantic_search_notes(user_id: str, embedding: list, match_count: int = 5) -> list[dict]:
    sb = db.get_supabase_client()
    res = sb.rpc(
        "match_notes",
        {"query_embedding": embedding, "match_user_id": user_id, "match_count": match_count},
    ).execute()
    return res.data or []


def get_notes(user_id: str) -> list[dict]:
    """Public accessor so app.py can show notes in the sidebar without touching internals."""
    return _list_notes(user_id)


def handle(name: str, args: dict, user_id: str) -> dict:
    if name == "add_note":
        content = args["content"].strip()
        embedding = get_embedding(content)
        row = _add_note(user_id, content, embedding)
        if not row:
            return {"status": "error", "message": "could not save note"}
        return {"status": "ok", "added": row["content"]}

    if name == "list_notes":
        notes = _list_notes(user_id)
        return {"status": "ok", "notes": [n["content"] for n in notes]}

    if name == "search_notes":
        embedding = get_embedding(args["query"])
        if not embedding:
            return {"status": "error", "message": "embedding unavailable"}
        results = _semantic_search_notes(user_id, embedding)
        return {"status": "ok", "matches": [{"content": r["content"], "similarity": round(r["similarity"], 3)} for r in results]}

    if name == "delete_note":
        query = args["note_query"]
        matches = _find_notes(user_id, query)
        if not matches:
            return {"status": "not_found", "query": query}
        if len(matches) > 1:
            return {"status": "ambiguous", "query": query, "candidates": [n["content"] for n in matches]}
        _delete_note(matches[0]["id"])
        return {"status": "ok", "deleted": matches[0]["content"]}

    return {"status": "error", "message": f"unknown notes tool {name}"}


connector = Connector(
    name="notes",
    description="Freeform notes and reference info the user wants to remember, without a deadline "
                "or action attached (e.g. passwords, preferences, ideas).",
    tools=TOOLS,
    handle=handle,
    system_prompt=SYSTEM_PROMPT,
)
