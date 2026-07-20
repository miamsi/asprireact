"""Todos connector: add/list/complete/reopen/reschedule/delete/search time-aware tasks."""
import db
from jina_client import get_embedding
from time_utils import humanize_due
from .base import Connector

CATEGORY_EMOJI = {
    "work": "\U0001F4BC", "personal": "\U0001F642", "errand": "\U0001F3C3",
    "health": "\U0001FA7A", "finance": "\U0001F4B0", "shopping": "\U0001F6D2",
    "study": "\U0001F4DA", "other": "\U0001F4CC",
}
PRIORITY_EMOJI = {"high": "\U0001F534", "medium": "\U0001F7E1", "low": "\U0001F7E2"}


SYSTEM_PROMPT = """
TODOS — TIME AWARENESS (important):
- Whenever the user mentions timing — "tomorrow", "tonight", "next Monday", "in 2 hours",
  "this weekend", "on the 15th", "next week" — resolve it into an absolute ISO 8601 datetime
  relative to the current moment given above, and pass it as `due_at` when adding or
  rescheduling a task.
- If a date is given without a specific time, default the time to 09:00.
- If the user gives no timing info at all, omit `due_at` entirely — don't invent a date.

TODOS — SMART CLASSIFICATION (important):
- For every task you add, infer `category` (work, personal, errand, health, finance, shopping,
  study, or other) and `priority` (low, medium, high) from context, even if the user didn't state
  them. Words like "urgent", "asap", "important", "deadline" imply high priority. Routine chores
  default to medium. Vague someday-maybe items default to low.
- Don't infer category purely from how a word sounds or looks (e.g. an app/system/project name
  that happens to resemble an unrelated everyday word). If a task references something you don't
  actually recognize, prefer "work" or "other" over guessing based on surface similarity.
- If the user says a task was tagged wrong ("that's actually work, not health"), use
  reclassify_todo to fix it — don't just apologize in text.

TODOS — OTHER RULES:
- When adding a task, extract just the core task text (strip filler like "please", "remind me to",
  "add", "to my list") but keep it natural and readable.
- Treat statements about a task already being done — "I checked X", "I already did X", "done with
  X", "finished X" — as a request to call complete_todo, exactly the same as an explicit command.
- When the user refers to a task loosely ("the milk one"), pass their wording as task_query and
  let the tool resolve it.
- complete_todo, reopen_todo, and delete_todo can match more than one task if the wording is broad.
  If the user's phrasing implies every matching task ("all", "both", "every", plural wording), set
  match_all=true. Otherwise leave it false.
- If a tool result comes back with status "ambiguous", more than one task matched and match_all
  was not set — don't guess, list the candidates and ask which one(s) they mean.
- If a tool result comes back with status "duplicate", a very similar open task already exists —
  tell the user instead of adding a new one.
- Use list_todos with filter="today"/"overdue"/"upcoming" when the user asks what's due soon.
- Mention due dates in natural human language ("tomorrow at 9am"), not raw ISO text.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": "Add a new task or reminder to the user's to-do list, with smart "
                           "time, category, and priority detection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The core task text to add."},
                    "due_at": {
                        "type": "string",
                        "description": "Absolute ISO 8601 datetime this task is due, resolved from "
                                       "any relative time the user mentioned. Omit if no timing given.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["work", "personal", "errand", "health", "finance", "shopping", "study", "other"],
                        "description": "Best-guess category for the task.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Best-guess urgency of the task.",
                    },
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "List the user's tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["all", "open", "done", "today", "overdue", "upcoming"],
                        "description": "Which tasks to show. 'today'=due today, 'overdue'=past due and "
                                       "not done, 'upcoming'=due in the next 7 days. Default 'open'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo",
            "description": "Mark a task as done, based on a description of the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_query": {"type": "string", "description": "Words describing which task to complete."},
                    "match_all": {"type": "boolean", "description": "True to complete every matching task."},
                },
                "required": ["task_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reopen_todo",
            "description": "Mark a previously completed task as not done / open again.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_query": {"type": "string", "description": "Words describing which task to reopen."},
                    "match_all": {"type": "boolean", "description": "True to reopen every matching task."},
                },
                "required": ["task_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_todo",
            "description": "Change the due date/time of an existing task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_query": {"type": "string", "description": "Words describing which task to reschedule."},
                    "due_at": {"type": "string", "description": "New absolute ISO 8601 datetime."},
                },
                "required": ["task_query", "due_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reclassify_todo",
            "description": "Correct the category and/or priority of an existing task — use this when "
                           "the user says a task was tagged wrong (e.g. \"that's actually work, not health\").",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_query": {"type": "string", "description": "Words describing which task to fix."},
                    "category": {
                        "type": "string",
                        "enum": ["work", "personal", "errand", "health", "finance", "shopping", "study", "other"],
                    },
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["task_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": "Permanently delete a task, based on a description of the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_query": {"type": "string", "description": "Words describing which task to delete."},
                    "match_all": {"type": "boolean", "description": "True to delete every matching task."},
                },
                "required": ["task_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_todos",
            "description": "Semantically search the user's tasks for ones related to a topic or meaning, "
                           "even if the exact words don't match.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What the user is looking for."}},
                "required": ["query"],
            },
        },
    },
]


def _fmt(t: dict) -> dict:
    return {
        "task": t["task"],
        "is_done": t["is_done"],
        "due": humanize_due(t.get("due_at")),
        "category": t.get("category", "other"),
        "priority": t.get("priority", "medium"),
    }


def handle(name: str, args: dict, user_id: str) -> dict:
    if name == "add_todo":
        task = args["task"].strip()
        embedding = get_embedding(task)

        # Duplicate guard: skip adding if a near-identical open task already exists.
        if embedding:
            candidates = db.semantic_search(user_id, embedding, match_count=1)
            if candidates and not candidates[0]["is_done"] and candidates[0]["similarity"] >= 0.90:
                return {"status": "duplicate", "existing": _fmt(candidates[0])}

        row = db.add_todo(
            user_id, task, embedding,
            due_at=args.get("due_at"), category=args.get("category"), priority=args.get("priority"),
        )
        if not row:
            return {"status": "error", "message": "could not save task"}
        return {"status": "ok", "added": _fmt(row)}

    if name == "list_todos":
        filt = args.get("filter", "open")
        todos = db.list_todos(user_id, filter=filt)
        return {"status": "ok", "filter": filt, "todos": [_fmt(t) for t in todos]}

    if name in ("complete_todo", "reopen_todo", "delete_todo", "reschedule_todo", "reclassify_todo"):
        query = args["task_query"]
        match_all = bool(args.get("match_all", False))
        status = "done" if name == "reopen_todo" else "open"
        matches = db.find_matching_todos(user_id, query, status=status)

        if not matches:
            emb = get_embedding(query)
            if emb:
                results = db.semantic_search(user_id, emb, match_count=3)
                wanted_done = (status == "done")
                results = [r for r in results if r.get("is_done", False) == wanted_done]
                if results:
                    matches = [results[0]]
        if not matches:
            return {"status": "not_found", "query": query}

        if name == "reschedule_todo":
            match = matches[0]
            updated = db.reschedule_todo(match["id"], args.get("due_at"))
            return {"status": "ok", "rescheduled": match["task"], "new_due": humanize_due(updated.get("due_at"))}

        if name == "reclassify_todo":
            match = matches[0]
            updated = db.reclassify_todo(match["id"], category=args.get("category"), priority=args.get("priority"))
            if not updated:
                return {"status": "error", "message": "nothing to update"}
            return {
                "status": "ok",
                "reclassified": match["task"],
                "category": updated.get("category"),
                "priority": updated.get("priority"),
            }

        if len(matches) > 1 and not match_all:
            return {"status": "ambiguous", "query": query, "candidates": [t["task"] for t in matches]}

        targets = matches if match_all else matches[:1]
        done_list = []
        for t in targets:
            if name == "complete_todo":
                db.complete_todo(t["id"])
            elif name == "reopen_todo":
                db.reopen_todo(t["id"])
            elif name == "delete_todo":
                db.delete_todo(t["id"])
            done_list.append(t["task"])

        key = {"complete_todo": "completed", "reopen_todo": "reopened", "delete_todo": "deleted"}[name]
        return {"status": "ok", key: done_list}

    if name == "search_todos":
        query = args["query"]
        emb = get_embedding(query)
        if not emb:
            return {"status": "error", "message": "embedding unavailable"}
        results = db.semantic_search(user_id, emb, match_count=5)
        return {"status": "ok", "matches": [{**_fmt(r), "similarity": round(r["similarity"], 3)} for r in results]}

    return {"status": "error", "message": f"unknown todos tool {name}"}


connector = Connector(
    name="todos",
    description="Time-aware to-do list and reminders: adding, listing, completing, rescheduling, "
                "deleting, or searching tasks with due dates, categories, and priorities.",
    tools=TOOLS,
    handle=handle,
    system_prompt=SYSTEM_PROMPT,
)
