# ✅ To-Do Chat

A chatbot-style to-do & reminder list. Talk to it in plain English — "remind me to check my
inbox about the performance review tomorrow at 10am", "what's due today?", "reschedule the inbox
task to Friday", "find anything about work" — and it understands **when**, **what kind of task**,
and **how urgent** it is, without you filling out any forms.

**Stack**
- **Streamlit** – chat UI + login screens
- **Supabase** – user auth (email/password) + Postgres database (with `pgvector` for search)
- **Groq** – fast LLM (Llama 3.3) that reads your message, resolves dates/times, classifies the
  task, and decides which action to take
- **Jina AI** – text embeddings, used for semantic search and fuzzy task lookup

## What's "smart" about it

- **Time-aware**: "tomorrow", "next Monday", "in 2 hours", "this weekend" all get resolved into
  a real due date/time, relative to the current moment in your configured timezone — not just
  stored as literal text.
- **Auto-categorized**: every task is tagged work / personal / errand / health / finance /
  shopping / study / other, inferred from context.
- **Auto-prioritized**: words like "urgent" or "asap" bump priority to high; routine chores land
  at medium; vague someday-items default to low.
- **Reminder-aware views**: ask "what's overdue?" or "what's due today?", or just open the app —
  overdue and due-today tasks surface as banners automatically. The sidebar also has Today /
  Overdue / Upcoming (7 days) / Done / All filters.
- **Reschedulable**: "push the dentist thing to next week" updates the due date without deleting
  and re-adding the task.
- **Resilient tool-calling**: Groq's Llama models occasionally emit a malformed function-call
  string instead of clean JSON; the app recovers from that automatically instead of crashing.

## Architecture: pluggable connectors, not a hardcoded tool list

This isn't a single monolithic prompt with every tool bolted on. It's a small **connector
registry**:

- Each domain (**todos**, **notes**, whatever you add next) is a self-contained connector: its
  own tool schemas, its own execution logic, its own system-prompt instructions.
- A lightweight **router** call looks at your message first and decides which connector(s) are
  actually relevant, so the main tool-calling call only ever sees the tools it might need — not
  every tool in the app. This keeps tool-selection accurate and prompts small even as you add
  more connectors.
- Whatever tool Groq ends up calling gets **dispatched through the registry** to whichever
  connector owns it — `agent.py` itself has zero knowledge of what a "todo" or a "note" even is.

This is deliberately *not* an architecture where the LLM writes and executes new tools on the
fly — letting a model generate and run arbitrary code at request time is a real security risk in
a shared app. Instead, new capabilities are added by a developer writing a small, reviewable
connector module, and the *routing* between them is what's dynamic.

```
connectors/
├── base.py     # the Connector interface: name, description, tools, handle(), system_prompt
├── todos.py    # the to-do/reminder connector (from the original app)
├── notes.py    # a second connector — freeform notes, proves the architecture generalizes
└── __init__.py # registry: ALL_CONNECTORS, tool ownership lookup, dynamic tool/prompt loading
```

### Adding your own connector

1. Create `connectors/your_thing.py`.
2. Define `TOOLS` (Groq/OpenAI-style function schemas), a `handle(name, args, user_id) -> dict`
   function that executes them, and optionally a `SYSTEM_PROMPT` string with domain-specific
   instructions.
3. Build your own data access (a new Supabase table + RLS policies, following the pattern in
   `supabase_schema.sql` / `migration_add_notes.sql`).
4. At the bottom of the file: `connector = Connector(name="your_thing", description="...",
   tools=TOOLS, handle=handle, system_prompt=SYSTEM_PROMPT)`.
5. Register it in `connectors/__init__.py`'s `ALL_CONNECTORS` dict.

That's it — `agent.py`, the router, and the dispatch logic never need to change.

## 1. Project files

```
todo-chatbot/
├── app.py                       # Streamlit app: login + chat UI + reminder banners
├── agent.py                     # Orchestrator: router + dynamic tool loading + dispatch
├── connectors/
│   ├── base.py                  # Connector interface
│   ├── todos.py                 # Todos connector (time/category/priority aware)
│   ├── notes.py                 # Notes connector (proves the architecture generalizes)
│   └── __init__.py              # Registry
├── db.py                        # Supabase auth + todos data access, smart filtering
├── time_utils.py                # Timezone-aware date parsing/formatting helpers
├── jina_client.py                # Jina AI embeddings wrapper
├── requirements.txt
├── supabase_schema.sql          # Run this once in Supabase's SQL editor (todos + auth)
├── migration_add_notes.sql      # Run this once to add the notes table
├── .streamlit/
│   └── secrets.toml.example     # Copy to secrets.toml and fill in your keys
└── .gitignore
```

## 2. Set up Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **Authentication → Providers** and make sure **Email** is enabled (it is by default).
   Optionally turn off "Confirm email" for faster testing.
3. Go to **SQL Editor → New query**, paste the contents of `supabase_schema.sql`, and run it.
   This creates the `todos` table (with `due_at`, `category`, `priority` columns), enables
   `pgvector`, sets up Row Level Security so users can only see their own tasks, and adds a
   `match_todos` function for semantic search.
   - **Already had the table from before?** Just run the three commented `alter table` lines
     near the top of the file to add the new columns without losing data.
4. Also run `migration_add_notes.sql` to create the `notes` table used by the Notes connector.
5. Go to **Project Settings → API** and copy:
   - **Project URL** → `supabase.url`
   - **anon public key** → `supabase.anon_key`

## 3. Get API keys

- **Groq**: create a free key at [console.groq.com/keys](https://console.groq.com/keys).
- **Jina AI**: create a free key at [jina.ai/embeddings](https://jina.ai/embeddings) (click "Get
  API key").

## 4. Configure secrets

Copy the example file and fill in your real values:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

```toml
[supabase]
url = "https://YOUR-PROJECT-REF.supabase.co"
anon_key = "YOUR_SUPABASE_ANON_PUBLIC_KEY"

[groq]
api_key = "YOUR_GROQ_API_KEY"
model = "llama-3.3-70b-versatile"

[jina]
api_key = "YOUR_JINA_API_KEY"
embedding_model = "jina-embeddings-v2-base-en"

[app]
timezone = "Asia/Jakarta"   # any IANA timezone, e.g. "America/New_York", "Europe/London", "UTC"
```

Set `[app].timezone` to wherever you actually are — it's what "today" and "tomorrow" get
resolved against. `secrets.toml` is already in `.gitignore` — never commit it.

## 5. Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL Streamlit prints, sign up with an email + password, and start chatting.

## 6. Push to GitHub

```bash
git init
git add .
git commit -m "To-do chatbot: Streamlit + Supabase + Groq + Jina, time-aware"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/todo-chatbot.git
git push -u origin main
```

Because `secrets.toml` is gitignored, only `secrets.toml.example` gets pushed — your real keys
stay local.

## 7. Deploy on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **New app**, pick your `todo-chatbot` repo, branch `main`, main file `app.py`.
3. Open **Advanced settings → Secrets** and paste the same content as your local
   `secrets.toml` (including the `[app]` timezone block above).
4. Click **Deploy**. Your chatbot to-do app will be live at a `*.streamlit.app` URL.

## How the chat logic works

1. Your message goes to `agent.py`, which tells Groq the current date/time (via
   `time_utils.now_label()`) and offers a set of tools: `add_todo`, `list_todos`,
   `complete_todo`, `reopen_todo`, `reschedule_todo`, `delete_todo`, `search_todos`.
2. Groq resolves any relative time ("tomorrow at 10am") into an absolute ISO datetime, infers a
   category and priority, and picks the right tool — e.g. "remind me to check my inbox about the
   performance review tomorrow" → `add_todo(task="check inbox about performance review",
   due_at="2026-07-09T09:00:00", category="work", priority="medium")`.
3. `agent.py` runs that tool against `db.py` (Supabase). For adds and searches,
   `jina_client.py` generates a text embedding so tasks can later be found by meaning.
4. The tool's result goes back to Groq, which writes a short, natural reply mentioning the due
   date in plain language (e.g. "Got it — I'll remind you tomorrow at 10am 🗓️").
5. The sidebar and top-of-chat banners always reflect live data from Supabase: open tasks,
   what's overdue, what's due today, and what's coming up in the next 7 days.

## Notes / things you can extend

- Add recurring reminders (e.g. "every Monday") by extending the schema with a `recurrence`
  field and a small scheduler.
- Wire up real push/email notifications for due reminders using a Supabase Edge Function + cron,
  since Streamlit itself has no background process.
- Swap the Groq model in `secrets.toml` (e.g. `llama-3.1-8b-instant` for lower latency).
- Add a minimum similarity cutoff in `db.semantic_search` / `match_todos` if semantic search
  ever feels too loose.
