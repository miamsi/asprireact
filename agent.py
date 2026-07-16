"""
Groq-powered orchestrator.

This module doesn't know anything about todos or notes specifically — it only knows how to:
1. ask a fast, cheap "router" call which connectors are relevant to the user's message,
2. load only those connectors' tool schemas into the main tool-calling call (keeps prompts small
   and tool-selection accurate as more connectors get added),
3. dispatch any tool call Groq makes to whichever connector owns that tool, via the registry,
4. recover gracefully if Groq emits a malformed tool-call instead of crashing.

Adding a new capability = adding a new connector module. This file never needs to change.
"""
import json
import re
import streamlit as st
from groq import Groq, BadRequestError, RateLimitError

import model_selector
from connectors import ALL_CONNECTORS, get_connector_for_tool, tools_for, prompts_for
from time_utils import now_label

# Re-exported for app.py, which displays these in the sidebar.
from connectors.todos import CATEGORY_EMOJI, PRIORITY_EMOJI  # noqa: F401


def _base_system_prompt(active_connectors: list[str]) -> str:
    return f"""You are a sharp, time-aware personal assistant living inside a chat app.

Right now it is: {now_label()}.

You have access to the following capabilities right now: {", ".join(active_connectors)}.
Always use a tool when the user wants to add, list, complete, reschedule, delete, or search
something that fits one of your capabilities. Only reply with plain text (no tool call) for
greetings, small talk, or clarifying questions.

{prompts_for(active_connectors)}

GENERAL RULES:
- Keep your final spoken replies short, warm, and conversational. Use at most one emoji.
"""


@st.cache_resource
def get_groq_client() -> Groq:
    return Groq(api_key=st.secrets["groq"]["api_key"])


# ---------------------------------------------------------------------------
# Router: decide which connectors are relevant to this message
# ---------------------------------------------------------------------------

def _route_connectors(client, model, user_message: str) -> list[str]:
    """
    Fast, cheap classification call: which connector(s) does this message need?
    Falls back to ALL connectors if the call fails or returns nothing usable — better to load
    a few extra tools than to silently drop a capability the user needed.
    """
    if len(ALL_CONNECTORS) <= 1:
        return list(ALL_CONNECTORS.keys())

    catalogue = "\n".join(f"- {c.name}: {c.description}" for c in ALL_CONNECTORS.values())
    prompt = (
        "Given the catalogue of capabilities below, return a JSON array of the capability names "
        "relevant to the user's message. If the message is generic (greeting, small talk, unclear) "
        f"or could need more than one, include all of them.\n\nCapabilities:\n{catalogue}\n\n"
        f'User message: "{user_message}"\n\nRespond with ONLY a JSON array, e.g. ["todos"].'
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=60,
        )
        text = resp.choices[0].message.content or ""
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            names = [n for n in json.loads(match.group(0)) if n in ALL_CONNECTORS]
            if names:
                return names
    except Exception:
        pass
    return list(ALL_CONNECTORS.keys())


# ---------------------------------------------------------------------------
# Resilience against Groq's occasional malformed tool-call output
# ---------------------------------------------------------------------------

def _extract_failed_generation(err: BadRequestError) -> str | None:
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        # Groq occasionally returns a body where "error" is mapped to None instead of a dict.
        # We must default to an empty dict so .get("failed_generation") doesn't crash on NoneType.
        error_dict = body.get("error") or {}
        return error_dict.get("failed_generation")
    text = str(err)
    match = re.search(r"'failed_generation':\s*'(.*)'\s*\}\s*\}?\s*$", text, re.DOTALL)
    if match:
        return match.group(1).encode().decode("unicode_escape")
    return None


def _recover_malformed_tool_call(text: str):
    """
    Recover name+args from malformed tool-call output. Groq's Llama models have been observed
    emitting at least two broken variants:
      <function=add_todo{"task": "x"}</function>
      <function=add_todo>{"task": "x"}</function>   (note the extra '>')
    This handles both.
    """
    match = re.search(r"<function=(\w+)>?\s*(\{.*)", text, re.DOTALL)
    if not match:
        return None
    name = match.group(1)
    raw_args = re.sub(r"</function>.*$", "", match.group(2), flags=re.DOTALL).strip()
    depth, end = 0, None
    for i, ch in enumerate(raw_args):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return None
    try:
        return name, json.loads(raw_args[:end])
    except json.JSONDecodeError:
        return None


def _looks_malformed(text: str) -> bool:
    return "<function=" in (text or "")


READ_ONLY_TOOLS = {"list_todos", "search_todos", "list_notes", "search_notes"}


def _call_with_tools(client, model_candidates: list[str], messages, tools):
    """
    Try each candidate model in Supabase-driven priority order (see model_selector.py).

    Returns (result, model_used):
      - result is a ChatCompletion on success,
      - or a (name, args) tuple if a malformed tool-call was salvaged from a broken response,
      - or None if every candidate failed (model_used is also None in that case).

    On a real rate limit (groq.RateLimitError — NOT BadRequestError, which is a 400 for a
    different kind of bad request entirely), the model is marked rate-limited in Supabase with a
    cooldown, so every session/instance skips it on subsequent requests instead of each one
    rediscovering the same 429 independently on every message.
    """
    for model in model_candidates:
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, tools=tools, tool_choice="auto", temperature=0.2,
            )
            return resp, model
        except RateLimitError:
            model_selector.mark_rate_limited(model)
            continue
        except BadRequestError as e:
            failed_generation = _extract_failed_generation(e)
            if failed_generation:
                recovered = _recover_malformed_tool_call(failed_generation)
                if recovered:
                    return recovered, model
            continue  # this model's tool-calling glitched; the next candidate may not
        except Exception:
            continue
    return None, None


def _plain_complete(client, model_candidates: list[str], messages, temperature: float = 0.3):
    """Same model-fallback behavior as _call_with_tools, for calls that don't need tools."""
    for model in model_candidates:
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
            return resp.choices[0].message.content, model
        except RateLimitError:
            model_selector.mark_rate_limited(model)
            continue
        except Exception:
            continue
    return None, None


def _finish_after_tool(client, model_candidates: list[str], messages, name, args, result):
    """
    Shared tail for a recovered/malformed tool call: tell the model what happened via a SYSTEM
    note (not a fake 'assistant' turn) so it answers naturally instead of echoing back internal
    plumbing like "Calling list_todos with {...}" — which is exactly what leaked into replies
    when this was phrased as an assistant message the model could parrot.
    """
    messages.append({
        "role": "system",
        "content": (
            f"[internal only — do not repeat this to the user] You just performed the action "
            f"'{name}' with parameters {json.dumps(args)}. Result: {json.dumps(result)}. "
            f"Now reply to the user naturally and briefly, as if you simply did the thing. "
            f"Never mention tool or function names, parameters, or the word 'calling'."
        ),
    })
    text, _ = _plain_complete(client, model_candidates, messages)
    return text or "Done!"


def _dispatch(user_id: str, name: str, args: dict) -> dict:
    """Route a tool call to whichever connector owns it."""
    conn = get_connector_for_tool(name)
    if conn is None:
        return {"status": "error", "message": f"no connector handles tool '{name}'"}
    return conn.handle(name, args, user_id)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent(user_id: str, chat_history: list[dict], user_message: str) -> tuple[str, bool]:
    """
    chat_history: list of {"role": "user"|"assistant", "content": str} from prior turns.
    Returns (reply_text, changed) where `changed` is True if any tool call mutated data (added,
    completed, deleted, rescheduled a task/note) — used by the UI to decide whether the sidebar
    needs a full refresh, versus a pure read (list/search) which doesn't.
    """
    client = get_groq_client()
    preferred_model = st.secrets["groq"].get("model", "meta-llama/llama-4-scout-17b-16e-instruct")
    model_candidates = model_selector.get_ordered_models(fallback_default=preferred_model)

    active = _route_connectors(client, model_candidates[0], user_message)
    tools = tools_for(active)

    messages = [{"role": "system", "content": _base_system_prompt(active)}]
    messages += chat_history
    messages.append({"role": "user", "content": user_message})

    first, used_model = _call_with_tools(client, model_candidates, messages, tools)

    if first is None:
        text, _ = _plain_complete(client, model_candidates, messages)
        if text:
            return text, False
        return "Sorry, I'm having trouble reaching the model right now — please try again shortly.", False

    if isinstance(first, tuple):
        # Recovered directly from a broken response (malformed tool-call syntax).
        name, args = first
        result = _dispatch(user_id, name, args)
        changed = name not in READ_ONLY_TOOLS
        return _finish_after_tool(client, model_candidates, messages, name, args, result), changed

    msg = first.choices[0].message

    if not msg.tool_calls:
        content = msg.content or ""
        # Second failure mode: the API call succeeded, but the model's plain-text content is
        # itself malformed pseudo tool-call syntax that never triggered Groq's error path.
        if _looks_malformed(content):
            recovered = _recover_malformed_tool_call(content)
            if recovered:
                name, args = recovered
                result = _dispatch(user_id, name, args)
                changed = name not in READ_ONLY_TOOLS
                return _finish_after_tool(client, model_candidates, messages, name, args, result), changed
        return content or "...", False

    messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls})
    changed = False
    for call in msg.tool_calls:
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        if call.function.name not in READ_ONLY_TOOLS:
            changed = True
        result = _dispatch(user_id, call.function.name, args)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

    text, _ = _plain_complete(client, model_candidates, messages)
    if text:
        return text, changed
    return "Done — but I had trouble phrasing a reply. Check your task list in the sidebar!", changed
