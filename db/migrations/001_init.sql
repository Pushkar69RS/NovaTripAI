-- 001_init: extensions and core tables for travel-yantra.
-- Applied via the Supabase MCP (apply_migration) on 2026-08-27.

create extension if not exists vector with schema extensions;
create extension if not exists pg_trgm with schema extensions;

create table poi (
  id bigint generated always as identity primary key,
  name text not null,
  name_kn text,
  city text not null,
  district text,
  lat double precision not null,
  lng double precision not null,
  category text not null check (category in ('temple','monument','museum','nature','viewpoint','market','food','experience')),
  tags text[] not null default '{}',
  typical_dwell_min int not null check (typical_dwell_min > 0),
  entry_fee_inr int not null default 0,
  opens time,
  closes time,
  closed_on int[] not null default '{}',  -- ISO weekday: 1=Mon .. 7=Sun
  best_time text,
  accessibility_notes text,
  elderly_friendly boolean not null default true,
  popularity int check (popularity between 1 and 5),
  source_url text,
  last_verified date,
  trust text not null default 'draft' check (trust in ('verified','draft')),
  unique (name, city)
);

create table poi_edge (
  from_poi bigint not null references poi(id) on delete cascade,
  to_poi bigint not null references poi(id) on delete cascade,
  relation text not null check (relation in ('same_dynasty','same_style','pairs_well_with','nearby')),
  weight real default 1.0,
  primary key (from_poi, to_poi, relation)
);

create table intercity_leg (
  id bigint generated always as identity primary key,
  from_city text not null,
  to_city text not null,
  mode text not null check (mode in ('car','bus','train')),
  distance_km int,
  duration_min int not null,
  is_estimated boolean not null default true,
  notes text
);

create table advisory (
  id bigint generated always as identity primary key,
  poi_id bigint references poi(id) on delete cascade,
  city text,
  severity text not null check (severity in ('info','warning','closed')),
  message text not null,
  source text not null,
  valid_from date not null default current_date,
  valid_until date not null,
  created_by text not null default 'rohan'
);

create table doc_chunk (
  id bigint generated always as identity primary key,
  poi_id bigint references poi(id) on delete set null,
  city text,
  title text,
  body text not null,
  chunk_type text not null check (chunk_type in ('hook','story','fact','sensory','taste','practical')),
  is_legend boolean not null default false,
  lang text not null default 'en',
  source_name text,
  source_url text,
  last_verified date,
  body_tsv tsvector generated always as (to_tsvector('english', coalesce(title, '') || ' ' || body)) stored,
  embedding extensions.vector(384)
);
create index doc_chunk_body_tsv_idx on doc_chunk using gin (body_tsv);
create index doc_chunk_embedding_idx on doc_chunk using hnsw (embedding extensions.vector_cosine_ops);

create table trip (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  request jsonb not null,
  status text not null default 'draft',
  plan jsonb,
  alternatives jsonb
);

create table tour (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  trip_id uuid references trip(id) on delete set null,
  city text not null,
  duration_min int not null,
  depth text not null check (depth in ('quick','deep')),
  segments jsonb
);

create table eval_run (
  id bigint generated always as identity primary key,
  ran_at timestamptz not null default now(),
  metrics jsonb not null
);
