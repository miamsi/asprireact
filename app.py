import html
import streamlit as st

import db
from agent import run_agent, CATEGORY_EMOJI, PRIORITY_EMOJI
from connectors.notes import get_notes
from time_utils import humanize_due
from ui_theme import (
    inject_theme, render_header, render_banner, render_chat_bubble,
    render_task_card, render_note_card, render_empty,
)

st.set_page_config(page_title="To-Do Chat", page_icon="✅", layout="centered")
inject_theme()


# ---------------------------------------------------------------------------
# Session state setup
# ---------------------------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = None       # {"id": ..., "email": ...}
if "messages" not in st.session_state:
    st.session_state.messages = []     # [{"role": "user"/"assistant", "content": str}]
if "task_filter" not in st.session_state:
    st.session_state.task_filter = "Open"


# ---------------------------------------------------------------------------
# Auth screen
# ---------------------------------------------------------------------------
def auth_screen():
    render_header("✅ To-Do Chat", "Your to-do list, managed entirely by chatting — now with time-aware reminders.")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            try:
                res = db.sign_in(email, password)
                st.session_state.user = {"id": res.user.id, "email": res.user.email}
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab_signup:
        with st.form("signup_form"):
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password (min 6 characters)", type="password", key="signup_password")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            try:
                res = db.sign_up(email, password)
                if res.user and not res.session:
                    st.success("Account created! Check your email to confirm, then log in.")
                else:
                    st.session_state.user = {"id": res.user.id, "email": res.user.email}
                    st.rerun()
            except Exception as e:
                st.error(f"Sign up failed: {e}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
FILTER_OPTIONS = ["Open", "Today", "Overdue", "Upcoming", "Done", "All"]
FILTER_MAP = {
    "Open": "open", "Today": "today", "Overdue": "overdue",
    "Upcoming": "upcoming", "Done": "done", "All": "all",
}


def render_pill_filter():
    """Segmented pill control built from native buttons (primary = selected), styled via CSS.
    Laid out as two rows of 3 rather than one row of 6."""
    rows = [FILTER_OPTIONS[:3], FILTER_OPTIONS[3:]]
    for row in rows:
        cols = st.columns(len(row))
        for col, label in zip(cols, row):
            selected = st.session_state.task_filter == label
            if col.button(label, key=f"filter_{label}", type="primary" if selected else "secondary",
                          use_container_width=True):
                st.session_state.task_filter = label
                st.rerun()


def sidebar(user_id: str):
    with st.sidebar:
        st.markdown(f"**{st.session_state.user['email']}**")
        if st.button("Log out", use_container_width=True):
            db.sign_out()
            st.session_state.user = None
            st.session_state.messages = []
            st.rerun()

        st.divider()
        render_pill_filter()
        st.write("")

        todos = db.list_todos(user_id, filter=FILTER_MAP[st.session_state.task_filter])
        if not todos:
            render_empty("Nothing here — ask me to add something!")
        for t in todos:
            due_label = humanize_due(t.get("due_at"))
            category = t.get("category", "other")
            cat_emoji = CATEGORY_EMOJI.get(category, "\U0001F4CC")
            priority = t.get("priority", "medium")
            render_task_card(t, due_label, cat_emoji, category, priority)

        st.divider()
        notes = get_notes(user_id)
        with st.expander(f"\U0001F4DD Notes ({len(notes)})"):
            if not notes:
                render_empty('No notes yet — try "note that..."')
            for n in notes:
                render_note_card(n["content"])


# ---------------------------------------------------------------------------
# Chat screen
# ---------------------------------------------------------------------------
def chat_screen():
    user_id = st.session_state.user["id"]

    # 1. Render the static UI FIRST
    sidebar(user_id)

    render_header(
        "✅ To-Do Chat",
        'Try: "remind me to check my inbox about performance review tomorrow at 10am", '
        '"what\'s due today?", "note that the wifi password is x", "find anything about work"',
    )

    overdue = db.list_todos(user_id, filter="overdue")
    due_today = db.list_todos(user_id, filter="today")
    
    if overdue:
        names = ", ".join(t["task"] for t in overdue[:3]) + (", ..." if len(overdue) > 3 else "")
        render_banner("overdue", "⏰", f"{len(overdue)} overdue: {names}")
    if due_today:
        names = ", ".join(t["task"] for t in due_today[:3]) + (", ..." if len(due_today) > 3 else "")
        render_banner("today", "📅", f"Due today: {names}")

    # 2. Render all historical messages inside a container so we can append to it seamlessly
    chat_container = st.container()
    with chat_container:
        for m in st.session_state.messages:
            render_chat_bubble(m["role"], m["content"])

    # 3. Handle the Chat Input
    prompt = st.chat_input("Tell me what to do...")

    if prompt:
        # Instantly display user's message in the UI without waiting for a rerun
        with chat_container:
            render_chat_bubble("user", prompt)
        
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Create a placeholder at the bottom for the assistant's reply
        with chat_container:
            stream_container = st.empty()
        
        history = st.session_state.messages[-11:-1] # History excluding current prompt
        full_reply = ""
        changed = False

        try:
            # run_agent returns a tuple of (reply_text, changed)
            reply_text, changed = run_agent(user_id, history, prompt)
            full_reply = str(reply_text)
            
            # Use raw content instead of html.escape to allow Markdown
            final_html = f'<div class="tc-msg-row assistant"><div class="tc-bubble assistant">{full_reply}</div></div>'
            stream_container.markdown(final_html, unsafe_allow_html=True)

        except Exception as e:
            full_reply = f"Sorry, something went wrong on my end ({e}). Could you try again?"
            final_html = f'<div class="tc-msg-row assistant"><div class="tc-bubble assistant">{full_reply}</div></div>'
            stream_container.markdown(final_html, unsafe_allow_html=True)
        
        # Save the final reply to state
        st.session_state.messages.append({"role": "assistant", "content": full_reply})
        
        # ONLY refresh the entire page if the database was actually modified (tasks added/completed).
        # If it was just normal chatting, the page won't flash at all!
        if changed:
            st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if st.session_state.user is None:
    auth_screen()
else:
    chat_screen()
