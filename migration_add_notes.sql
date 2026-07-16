-- Run this once in the Supabase SQL editor to add the Notes connector's table.
-- Safe to run even if pgvector is already enabled (from the todos migration).

create extension if not exists vector;

create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  content text not null,
  embedding vector(768),
  created_at timestamptz not null default now()
);

create index if not exists notes_user_id_idx on public.notes(user_id);

alter table public.notes enable row level security;

drop policy if exists "Users can view their own notes" on public.notes;
create policy "Users can view their own notes"
  on public.notes for select
  using (auth.uid() = user_id);

drop policy if exists "Users can insert their own notes" on public.notes;
create policy "Users can insert their own notes"
  on public.notes for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users can delete their own notes" on public.notes;
create policy "Users can delete their own notes"
  on public.notes for delete
  using (auth.uid() = user_id);

-- Must drop first: Postgres won't let CREATE OR REPLACE change a function's return columns
drop function if exists match_notes(vector, uuid, integer);

create or replace function match_notes (
  query_embedding vector(768),
  match_user_id uuid,
  match_count int default 5
)
returns table (
  id uuid,
  content text,
  similarity float
)
language sql stable
as $$
  select
    notes.id,
    notes.content,
    1 - (notes.embedding <=> query_embedding) as similarity
  from notes
  where notes.user_id = match_user_id
    and notes.embedding is not null
  order by notes.embedding <=> query_embedding
  limit match_count;
$$;
