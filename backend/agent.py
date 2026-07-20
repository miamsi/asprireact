"""Groq-powered orchestrator."""
import os
import json
import re
from groq import Groq, BadRequestError, RateLimitError
from dotenv import load_dotenv

import model_selector
from connectors import ALL_CONNECTORS, get_connector_for_tool, tools_for, prompts_for
from time_utils import now_label

load_dotenv()

_groq_client_instance = None

def get_groq_client() -> Groq:
    global _groq_client_instance
    if _groq_client_instance is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Missing GROQ_API_KEY environment variable.")
        _groq_client_instance = Groq(api_key=api_key)
    return _groq_client_instance


def _base_system_prompt(active_connectors: list[str]) -> str:
    return f"""You are a sharp, time-aware personal assistant living inside a chat app.
Right now it is: {now_label()}.
You have access to the following capabilities right now: {", ".join(active_connectors)}.
Always use a tool when the user wants to add, list, complete, reschedule, delete, or search something.
{prompts_for(active_connectors)}
GENERAL RULES:
- Keep your final spoken replies short, warm, and conversational. Use at most one emoji.
"""

def _route_connectors(client, model, user_message: str) -> list[str]:
    if len(ALL_CONNECTORS) <= 1:
        return list(ALL_CONNECTORS.keys())
    catalogue = "\n".join(f"- {c.name}: {c.description}" for c in ALL_CONNECTORS.values())
    prompt = f'Capabilities:\n{catalogue}\n\nUser message: "{user_message}"\n\nRespond with ONLY a JSON array, e.g. ["todos"].'
    try:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=60
        )
        text = resp.choices[0].message.content or ""
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            names = [n for n in json.loads(match.group(0)) if n in ALL_CONNECTORS]
            if names: return names
    except Exception: pass
    return list(ALL_CONNECTORS.keys())

def _extract_failed_generation(err: BadRequestError) -> str | None:
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        error_dict = body.get("error") or {}
        return error_dict.get("failed_generation")
    text = str(err)
    match = re.search(r"'failed_generation':\s*'(.*)'\s*\}\s*\}?\s*$", text, re.DOTALL)
    if match: return match.group(1).encode().decode("unicode_escape")
    return None

def _recover_malformed_tool_call(text: str):
    match = re.search(r"<function=(\w+)>?\s*(\{.*)", text, re.DOTALL)
    if not match: return None
    name = match.group(1)
    raw_args = re.sub(r"</function>.*$", "", match.group(2), flags=re.DOTALL).strip()
    depth, end = 0, None
    for i, ch in enumerate(raw_args):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: { end := i + 1 }; break
    if end is None: return None
    try: return name, json.loads(raw_args[:end])
    except json.JSONDecodeError: return None

def _looks_malformed(text: str) -> bool:
    return "<function=" in (text or "")

READ_ONLY_TOOLS = {"list_todos", "search_todos", "list_notes", "search_notes"}

def _call_with_tools(client, model_candidates: list[str], messages, tools):
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
                if recovered: return recovered, model
            continue
        except Exception: continue
    return None, None

def _plain_complete(client, model_candidates: list[str], messages, temperature: float = 0.3):
    for model in model_candidates:
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
            return resp.choices[0].message.content, model
        except RateLimitError:
            model_selector.mark_rate_limited(model)
            continue
        except Exception: continue
    return None, None

def _finish_after_tool(client, model_candidates: list[str], messages, name, args, result):
    messages.append({
        "role": "system",
        "content": f"[internal] You performed '{name}' with {json.dumps(args)}. Result: {json.dumps(result)}. Reply naturally."
    })
    text, _ = _plain_complete(client, model_candidates, messages)
    return text or "Done!"

def _dispatch(user_id: str, name: str, args: dict) -> dict:
    conn = get_connector_for_tool(name)
    if conn is None: return {"status": "error", "message": f"no connector handles tool '{name}'"}
    return conn.handle(name, args, user_id)

def run_agent(user_id: str, chat_history: list[dict], user_message: str) -> tuple[str, bool]:
    client = get_groq_client()
    preferred_model = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    model_candidates = model_selector.get_ordered_models(fallback_default=preferred_model)

    active = _route_connectors(client, model_candidates[0], user_message)
    tools = tools_for(active)

    messages = [{"role": "system", "content": _base_system_prompt(active)}] + chat_history + [{"role": "user", "content": user_message}]
    first, used_model = _call_with_tools(client, model_candidates, messages, tools)

    if first is None:
        text, _ = _plain_complete(client, model_candidates, messages)
        if text: return text, False
        return "Sorry, I'm having trouble reaching the model right now.", False

    if isinstance(first, tuple):
        name, args = first
        result = _dispatch(user_id, name, args)
        return _finish_after_tool(client, model_candidates, messages, name, args, result), (name not in READ_ONLY_TOOLS)

    msg = first.choices[0].message
    if not msg.tool_calls:
        content = msg.content or ""
        if _looks_malformed(content):
            recovered = _recover_malformed_tool_call(content)
            if recovered:
                name, args = recovered
                result = _dispatch(user_id, name, args)
                return _finish_after_tool(client, model_candidates, messages, name, args, result), (name not in READ_ONLY_TOOLS)
        return content or "...", False

    messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls})
    changed = False
    for call in msg.tool_calls:
        try: args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError: args = {}
        if call.function.name not in READ_ONLY_TOOLS: changed = True
        result = _dispatch(user_id, call.function.name, args)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

    text, _ = _plain_complete(client, model_candidates, messages)
    return text or "Done!", changed
