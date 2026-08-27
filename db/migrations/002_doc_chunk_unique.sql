-- 002_doc_chunk_unique: give doc_chunk a natural key so seeding can upsert.
-- Without it a re-run either duplicates every paragraph or needs a TRUNCATE,
-- and CLAUDE.md rule 4 says destructive operations get asked about first.
-- Applied via the Supabase MCP (apply_migration) on 2026-08-28.

alter table doc_chunk add constraint doc_chunk_city_title_key unique (city, title);
