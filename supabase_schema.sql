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

-- 6. Safety & Audit
create table if not exists audit_log (
    id bigint primary key generated always as identity,
    timestamp timestamp with time zone default timezone('utc'::text, now()) not null,
    agent text not null,
    action_type text not null,
    details text not null default '',
    reasoning text not null default '',
    tier text not null default 'execute_with_confirmation',
    approved integer not null default 0,
    result text not null default ''
);

-- 7. Trading & Finance (Trading DB equivalent)
create table if not exists shadow_trades (
    id bigint primary key generated always as identity,
    ticker text not null,
    action text not null check(action in ('BUY','SELL','HOLD')),
    price_at_rec real not null,
    qty integer not null default 1,
    budget_used real not null default 0,
    signal_summary text not null default '',
    rec_date timestamp with time zone default timezone('utc'::text, now()) not null,
    eval_30d text,
    eval_60d text,
    eval_90d text,
    outcome text,
    sector text default '',
    notes text default ''
);

create table if not exists shadow_performance (
    id bigint primary key generated always as identity,
    snapshot_at timestamp with time zone default timezone('utc'::text, now()) not null,
    total_recs integer not null default 0,
    wins integer not null default 0,
    losses integer not null default 0,
    win_rate real not null default 0.0,
    notes text default ''
);

create table if not exists budget_transactions (
    id bigint primary key generated always as identity,
    amount real not null,
    tx_type text not null,
    category text not null,
    description text not null,
    timestamp timestamp with time zone default timezone('utc'::text, now()) not null
);

create table if not exists budget_categories (
    id bigint primary key generated always as identity,
    name text not null unique,
    limit_amount real not null
);

-- 8. Memory Management
create table if not exists memory_items (
    id bigint primary key generated always as identity,
    fact text not null,
    status text not null default 'active',
    last_reviewed timestamp with time zone default timezone('utc'::text, now()) not null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create table if not exists memory_review_log (
    id bigint primary key generated always as identity,
    fact_id bigint not null references memory_items(id) on delete cascade,
    review_date timestamp with time zone default timezone('utc'::text, now()) not null,
    action text not null
);

create table if not exists relationship_circles (
    id bigint primary key generated always as identity,
    name text not null unique,
    tone text not null default 'neutral'
);

create table if not exists circle_members (
    id bigint primary key generated always as identity,
    circle_id bigint not null references relationship_circles(id) on delete cascade,
    contact_id bigint not null references contacts(id) on delete cascade,
    unique(circle_id, contact_id)
);

-- 9. Infrastructure & Observability
create table if not exists latency_log (
    id bigint primary key generated always as identity,
    timestamp timestamp with time zone default timezone('utc'::text, now()) not null,
    agent text not null,
    command text not null,
    duration_ms integer not null,
    status text not null default 'success'
);
