-- 004_retired_and_tour_shape
--
-- doc_chunk.retired: a paragraph that no source file carries any more is
-- switched off rather than deleted. Retrieval ignores retired rows, the data
-- stays, and the flag flips back with one UPDATE. Deleting is Rohan's call
-- (CLAUDE.md rule 4), so the seed never does it.
--
-- tour gains what a Katha needs to be fetched back: the scope it was built
-- for, the language it was narrated in, and its word count.
-- Applied via the Supabase MCP (apply_migration) on 2026-08-28.

alter table doc_chunk add column retired boolean not null default false;
create index doc_chunk_live_idx on doc_chunk (city) where not retired;

alter table tour add column language text not null default 'en';
alter table tour add column scope jsonb;
alter table tour add column total_words int;
