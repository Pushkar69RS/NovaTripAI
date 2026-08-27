-- 003_doc_chunk_aliases: index the names of a place alongside its text.
--
-- The embedding is built from title + body + the names of the POI and the city,
-- in English and Kannada, because a paragraph rarely repeats the full official
-- name of what it describes. body_tsv only covered title + body, so the lexical
-- retriever was searching less text than the dense one and the comparison
-- between them was not fair. This puts both on the same material.
--
-- body_tsv is a generated column, so dropping and recreating it loses nothing:
-- every value is recomputed from columns that are still there.
-- Applied via the Supabase MCP (apply_migration) on 2026-08-28.

alter table doc_chunk add column aliases text;

drop index if exists doc_chunk_body_tsv_idx;
alter table doc_chunk drop column body_tsv;
alter table doc_chunk add column body_tsv tsvector
  generated always as (
    to_tsvector(
      'english',
      coalesce(title, '') || ' ' || body || ' ' || coalesce(aliases, '')
    )
  ) stored;
create index doc_chunk_body_tsv_idx on doc_chunk using gin (body_tsv);
