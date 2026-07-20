"""
Supabase-backed model selection for Groq calls.

Why this exists: Streamlit Cloud can run multiple instances of the app, and each chat message is
its own stateless request — an in-memory "this model is rate-limited, skip it" flag would only
ever be known to the one process that hit the 429, and would reset on every rerun anyway. Storing
the cooldown in Supabase instead means every session, every instance, and every future request
all see the same "model X is resting until time Y" state, so the app stops repeatedly retrying
(and re-failing against) an exhausted model on every single message.

The model list and priority order live in the `model_config` table (see
migration_add_model_config.sql) — editable directly in Supabase without a redeploy.
"""
from datetime import datetime, timedelta, timezone
import db

TABLE = "model_config"
DEFAULT_COOLDOWN_SECONDS = 60


def get_ordered_models(fallback_default: str) -> list[str]:
    """
    Returns Groq model names to try, in order:
      1. currently-available models, by priority (lowest first),
      2. currently-rate-limited models, as a last resort (better to retry a cooling-down model
         than to fail outright if literally everything else is also down),
      3. `fallback_default` appended if it isn't already somewhere in the list.

    Falls back to just [fallback_default] if Supabase is unreachable or the table is empty — a
    bookkeeping outage should never be the reason the app can't answer at all.
    """
    try:
        sb = db.get_supabase_client()
        res = sb.table(TABLE).select("*").order("priority").execute()
        rows = res.data or []
    except Exception:
        return [fallback_default]

    if not rows:
        return [fallback_default]

    now = datetime.now(timezone.utc)
    available, limited = [], []
    for r in rows:
        until = r.get("rate_limited_until")
        is_limited = False
        if until:
            try:
                from dateutil import parser as dateparser
                until_dt = dateparser.parse(until)
                if until_dt.tzinfo is None:
                    until_dt = until_dt.replace(tzinfo=timezone.utc)
                is_limited = until_dt > now
            except Exception:
                is_limited = False
        (limited if is_limited else available).append(r["model_name"])

    ordered = available + limited
    if fallback_default not in ordered:
        ordered.append(fallback_default)
    return ordered


def mark_rate_limited(model_name: str, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS) -> None:
    """Record that `model_name` just hit a rate limit, so every session skips it for a while."""
    try:
        sb = db.get_supabase_client()
        until = (datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)).isoformat()
        sb.table(TABLE).upsert({
            "model_name": model_name,
            "rate_limited_until": until,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass  # best-effort bookkeeping only — never let this crash the actual chat request
