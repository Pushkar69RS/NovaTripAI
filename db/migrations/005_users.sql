-- 005_users: four team accounts, and ownership of what they create.
--
-- The table is `app_user` because `user` is a reserved word in Postgres and
-- every query would otherwise need it quoted.
--
-- password_hash holds pbkdf2_sha256$<iterations>$<salt hex>$<digest hex>; the
-- plaintext never reaches the database (see app/accounts.py).
--
-- trip.user_id and tour.user_id are nullable so the rows that exist from the
-- walk-through survive the migration; scripts/seed_users.py adopts them.
-- Applied via the Supabase MCP (apply_migration) on 2026-08-28.

create table app_user (
  id bigint generated always as identity primary key,
  email text not null unique,
  name text not null,
  password_hash text not null,
  created_at timestamptz not null default now()
);

alter table trip add column user_id bigint references app_user(id) on delete cascade;
alter table tour add column user_id bigint references app_user(id) on delete cascade;
create index trip_user_idx on trip (user_id, created_at desc);
create index tour_user_idx on tour (user_id, created_at desc);
