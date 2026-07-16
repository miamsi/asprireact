"""
Custom visual identity for To-Do Chat.

Streamlit's stock components (disabled checkboxes as status icons, radio buttons as filters,
default chat bubbles) read as an unstyled internal tool. This module replaces that with an
intentional theme: a quiet, cool control-panel palette, with one consistent signature element —
monospace "departure board" time chips — used everywhere a due date appears, since the app's
whole job is telling you what's due and when.
"""
import html as _html
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');

:root {
  --tc-bg: #F5F6F9;
  --tc-bg-sidebar: #EDEFF5;
  --tc-ink: #1C2033;
  --tc-ink-muted: #6B7086;
  --tc-indigo: #33418C;
  --tc-indigo-soft: #E7E9F5;
  --tc-amber: #E2932E;
  --tc-amber-soft: #FBEBD3;
  --tc-red: #D6473C;
  --tc-red-soft: #FBE3E1;
  --tc-sage: #5E8C74;
  --tc-sage-soft: #E4EFE9;
  --tc-border: #DDE0EA;
}

html, body, .stApp {
  background-color: var(--tc-bg) !important;
  color: var(--tc-ink) !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
}

/* Disable Streamlit's default script-running fade/dimming effect to make chat seamless */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stSidebar"],
[data-testid="stHeader"] {
  opacity: 1 !important;
  transition: none !important;
}

[data-testid="stSidebar"] {
  background-color: var(--tc-bg-sidebar) !important;
  border-right: 1px solid var(--tc-border);
  z-index: 1000 !important;
}

h1, h2, h3, .tc-display {
  font-family: 'Bricolage Grotesque', sans-serif !important;
  color: var(--tc-ink) !important;
  letter-spacing: -0.01em;
}

/* Buttons: pill-shaped. Used for the segmented filter and log out.
   white-space: nowrap is critical here — without it, a narrow sidebar column forces button
   labels like "Overdue" to wrap one character per line instead of just staying on one line. */
.stButton > button {
  border-radius: 999px !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
  font-weight: 500 !important;
  font-size: 0.82rem !important;
  border: 1px solid var(--tc-border) !important;
  padding: 0.3rem 0.6rem !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  min-width: 0 !important;
  transition: all 0.15s ease;
}
.stButton > button p {
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}
.stButton > button[kind="primary"] {
  background-color: var(--tc-indigo) !important;
  border-color: var(--tc-indigo) !important;
}
.stButton > button[kind="secondary"] {
  background-color: transparent !important;
  color: var(--tc-ink-muted) !important;
}
.stButton > button[kind="secondary"]:hover {
  border-color: var(--tc-indigo) !important;
  color: var(--tc-indigo) !important;
}

/* Plain text inputs (login/signup forms) */
.stTextInput input {
  border-radius: 10px !important;
  border: 1px solid var(--tc-border) !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
}
.stTextInput input:focus {
  border-color: var(--tc-indigo) !important;
  box-shadow: 0 0 0 1px var(--tc-indigo) !important;
}

/* Flex-column layout so the chat input naturally lands at the bottom of the screen regardless of
   how much conversation exists — no fixed positioning, no hardcoded widths. The main content
   column becomes a full-height flex column; .st-key-chat_history (the message list) is the one
   flexible item that stretches to absorb all leftover vertical space and scrolls internally;
   chat_input is just the last, naturally-sized item in that column, which is what makes it sit at
   the bottom. overflow-y is `auto` rather than `hidden` here as a safety net — if content is ever
   taller than expected, the page scrolls normally as a fallback instead of clipping anything. */
[data-testid="stMain"] .block-container,
.main .block-container {
  display: flex !important;
  flex-direction: column !important;
  height: 100vh !important;
  overflow-y: auto !important;
  padding-bottom: 1rem !important;
}
.st-key-chat_history {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  overflow-y: auto !important;
  padding-right: 0.25rem !important;
}
[data-testid="stChatInput"] {
  flex: 0 0 auto !important;
}

/* Chat input itself. Positioning/sizing (making it land at the bottom of the screen) is handled
   by the flex-column rules above — this block only styles its appearance: single pill border
   (not a double box), and compact height instead of Streamlit's oversized default.

   height: auto below still matters: Streamlit wraps the textarea in its own hidden div with its
   own padding/min-height that was inflating the whole bar regardless of our own sizing — the
   nested "> div" rules strip that inner wrapper down to nothing so only our own sizing applies. */
[data-testid="stChatInput"] {
  height: auto !important;
  background: #fff !important;
  border: 1px solid var(--tc-border) !important;
  border-radius: 18px !important;
  padding: 4px 6px 4px 16px !important;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div {
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
[data-testid="stChatInput"]:focus-within {
  border-color: var(--tc-indigo) !important;
  box-shadow: 0 0 0 1px var(--tc-indigo) !important;
}
[data-testid="stChatInput"] textarea {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
  padding: 6px 0 !important;
  min-height: 10px !important;
  max-height: 120px !important;
  overflow-y: auto !important;
}
[data-testid="stChatInput"] textarea:focus {
  border: none !important;
  box-shadow: none !important;
}
[data-testid="stChatInput"] button {
  background: var(--tc-indigo) !important;
  border: none !important;
  border-radius: 999px !important;
  width: 30px !important;
  height: 30px !important;
  min-width: 30px !important;
  min-height: 30px !important;
  align-self: flex-end !important;
  margin-bottom: 2px !important;
}
[data-testid="stChatInput"] button svg { color: #fff !important; fill: #fff !important; }

/* We render our own chat bubbles — hide the default chat message chrome */
[data-testid="stChatMessage"] { display: none !important; }

/* Header block */
.tc-header { margin-bottom: 0.1rem; }
.tc-header h1 { font-size: 1.9rem; margin: 0; }
.tc-tagline { color: var(--tc-ink-muted); font-size: 0.92rem; margin-bottom: 1.1rem; }

/* Banners */
.tc-banner {
  border-radius: 10px;
  padding: 0.55rem 0.9rem;
  margin-bottom: 0.6rem;
  font-size: 0.92rem;
  border-left: 3px solid;
}
.tc-banner.overdue { background: var(--tc-red-soft); border-color: var(--tc-red); color: #7A231C; }
.tc-banner.today { background: var(--tc-amber-soft); border-color: var(--tc-amber); color: #7A4E0E; }

/* Chat bubbles */
.tc-msg-row { display: flex; margin: 0.45rem 0; }
.tc-msg-row.user { justify-content: flex-end; }
.tc-msg-row.assistant { justify-content: flex-start; }
.tc-bubble {
  max-width: 78%;
  padding: 0.55rem 0.85rem;
  border-radius: 14px;
  font-size: 0.94rem;
  line-height: 1.45;
  white-space: pre-wrap;
}
.tc-bubble.user {
  background: var(--tc-indigo);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.tc-bubble.assistant {
  background: #fff;
  color: var(--tc-ink);
  border: 1px solid var(--tc-border);
  border-bottom-left-radius: 4px;
}

/* Signature element: departure-board time chip, used for every due date/time */
.tc-chip {
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.1rem 0.45rem;
  border-radius: 5px;
  letter-spacing: 0.02em;
}
.tc-chip.overdue { background: var(--tc-red-soft); color: var(--tc-red); }
.tc-chip.today   { background: var(--tc-amber-soft); color: #94620E; }
.tc-chip.future  { background: var(--tc-indigo-soft); color: var(--tc-indigo); }
.tc-chip.none    { background: #EEF0F4; color: var(--tc-ink-muted); }
.tc-chip.done    { background: var(--tc-sage-soft); color: var(--tc-sage); }

/* Category tag */
.tc-tag {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--tc-ink-muted);
  margin-right: 0.35rem;
}

/* Task cards — replace the disabled-checkbox rows */
.tc-task {
  background: #fff;
  border: 1px solid var(--tc-border);
  border-left: 4px solid var(--tc-border);
  border-radius: 8px;
  padding: 0.5rem 0.7rem;
  margin-bottom: 0.45rem;
}
.tc-task.priority-high { border-left-color: var(--tc-red); }
.tc-task.priority-medium { border-left-color: var(--tc-amber); }
.tc-task.priority-low { border-left-color: var(--tc-sage); }
.tc-task.done { opacity: 0.55; }
.tc-task-title { font-size: 0.9rem; margin-top: 0.2rem; }
.tc-task-title.done-text { text-decoration: line-through; color: var(--tc-ink-muted); }

/* Notes cards */
.tc-note {
  background: #fff;
  border: 1px solid var(--tc-border);
  border-radius: 8px;
  padding: 0.45rem 0.65rem;
  margin-bottom: 0.4rem;
  font-size: 0.87rem;
}

.tc-empty { color: var(--tc-ink-muted); font-size: 0.85rem; padding: 0.4rem 0; }
</style>
"""


def inject_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def render_header(title: str, tagline: str):
    st.markdown(f'<div class="tc-header"><h1>{_html.escape(title)}</h1></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="tc-tagline">{_html.escape(tagline)}</div>', unsafe_allow_html=True)


def render_banner(kind: str, icon: str, text: str):
    st.markdown(f'<div class="tc-banner {kind}">{icon} {_html.escape(text)}</div>', unsafe_allow_html=True)


def render_chat_bubble(role: str, content: str):
    """
    Renders chat bubble with full Markdown support.
    We pass content directly to st.markdown to let the AI format its own responses
    (bolding, lists, etc.) without escaping the symbols.
    """
    st.markdown(
        f'<div class="tc-msg-row {role}"><div class="tc-bubble {role}">{content}</div></div>',
        unsafe_allow_html=True,
    )


def _chip_class(due_label: str, done: bool) -> str:
    if done:
        return "done"
    if not due_label:
        return "none"
    if due_label.startswith("Overdue"):
        return "overdue"
    if due_label.startswith("Today"):
        return "today"
    if due_label:
        return "future"
    

def render_task_card(task: dict, due_label: str, category_emoji: str, category: str, priority: str):
    done = task["is_done"]
    chip_class = _chip_class(due_label, done)
    chip_text = due_label if due_label else "no date"
    title_class = "tc-task-title done-text" if done else "tc-task-title"
    st.markdown(
        f'<div class="tc-task priority-{priority} {"done" if done else ""}">'
        f'<span class="tc-tag">{category_emoji} {_html.escape(category)}</span>'
        f'<span class="tc-chip {chip_class}">{_html.escape(chip_text)}</span>'
        f'<div class="{title_class}">{_html.escape(task["task"])}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_note_card(content: str):
    st.markdown(f'<div class="tc-note">{_html.escape(content)}</div>', unsafe_allow_html=True)


def render_empty(text: str):
    st.markdown(f'<div class="tc-empty">{_html.escape(text)}</div>', unsafe_allow_html=True)
