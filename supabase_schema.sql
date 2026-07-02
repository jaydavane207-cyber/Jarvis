-- Enable the pgvector extension to work with embeddings
create extension if not exists vector;

-- 1. Messages (Chat History)
create table if not exists messages (
    id bigint primary key generated always as identity,
    role text not null,
    content text not null, -- Store encrypted content from python
    timestamp timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Personal Store Tables
create table if not exists goals (
    id bigint primary key generated always as identity,
    title text not null, -- Encrypted
    description text, -- Encrypted
    progress integer default 0,
    status text default 'in_progress',
    target_date text,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create table if not exists health_logs (
    id bigint primary key generated always as identity,
    log_date text not null,
    log_type text not null,
    value text not null, -- Encrypted
    notes text -- Encrypted
);

create table if not exists financial_logs (
    id bigint primary key generated always as identity,
    log_date text not null,
    log_type text not null,
    amount real not null,
    category text, -- Encrypted
    description text -- Encrypted
);

create table if not exists memory_profile (
    key text primary key,
    value text not null -- Encrypted
);

-- 3. Reminders
create table if not exists reminders (
    id bigint primary key generated always as identity,
    text text not null,
    fire_at timestamp with time zone not null,
    fired integer default 0,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 4. CRM (Contacts and Interactions)
create table if not exists contacts (
    id bigint primary key generated always as identity,
    name text not null,
    phone text, -- Encrypted
    email text, -- Encrypted
    relationship text,
    notes text, -- Encrypted
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create table if not exists interactions (
    id bigint primary key generated always as identity,
    contact_id bigint not null references contacts(id) on delete cascade,
    type text not null default 'general',
    summary text not null, -- Encrypted
    timestamp timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 5. Vector Store (ChromaDB Replacement)
create table if not exists jarvis_memory (
    id uuid primary key default gen_random_uuid(),
    role text not null,
    content text not null,
    embedding vector(384), -- sentence-transformers all-MiniLM-L6-v2 uses 384 dimensions
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Vector Search Function
create or replace function match_jarvis_memory (
  query_embedding vector(384),
  match_threshold float,
  match_count int
)
returns table (
  id uuid,
  role text,
  content text,
  similarity float
)
language sql stable
as $$
  select
    jarvis_memory.id,
    jarvis_memory.role,
    jarvis_memory.content,
    1 - (jarvis_memory.embedding <=> query_embedding) as similarity
  from jarvis_memory
  where 1 - (jarvis_memory.embedding <=> query_embedding) > match_threshold
  order by jarvis_memory.embedding <=> query_embedding
  limit match_count;
$$;
