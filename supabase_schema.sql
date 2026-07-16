-- Run this in the Supabase SQL editor (Project -> SQL Editor -> New query)

-- 1. Enable the pgvector extension (needed for semantic search over todos)
create extension if not exists vector;

-- 2. Todos table
create table if not exists public.todos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  task text not null,
  is_done boolean not null default false,
  embedding vector(768),          -- jina-embeddings-v2-base-en outputs 768 dims
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists todos_user_id_idx on public.todos(user_id);

-- 3. Row Level Security: each user can only see/touch their own todos
alter table public.todos enable row level security;

create policy "Users can view their own todos"
  on public.todos for select
  using (auth.uid() = user_id);

create policy "Users can insert their own todos"
  on public.todos for insert
  with check (auth.uid() = user_id);

create policy "Users can update their own todos"
  on public.todos for update
  using (auth.uid() = user_id);

create policy "Users can delete their own todos"
  on public.todos for delete
  using (auth.uid() = user_id);

-- 4. Function for semantic ("find something like...") search using cosine distance
create or replace function match_todos (
  query_embedding vector(768),
  match_user_id uuid,
  match_count int default 5
)
returns table (
  id uuid,
  task text,
  is_done boolean,
  similarity float
)
language sql stable
as $$
  select
    todos.id,
    todos.task,
    todos.is_done,
    1 - (todos.embedding <=> query_embedding) as similarity
  from todos
  where todos.user_id = match_user_id
    and todos.embedding is not null
  order by todos.embedding <=> query_embedding
  limit match_count;
$$;

-- Note: in Supabase, sign-up/sign-in is handled by the built-in `auth` schema
-- (Authentication -> Providers -> Email, enabled by default). No extra table needed.
