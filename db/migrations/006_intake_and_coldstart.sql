-- 006_intake_and_coldstart: the new intake shape, cold-started cities, and the
-- Katha city layer.
--
-- poi.trust gains 'ai_generated' for rows a model drafted for a city nobody
-- has seeded; doc_chunk gains theme/tier for the deterministic city Katha;
-- city_centre holds one centre per city so an unseeded origin or destination
-- can still be placed on the map; trip keeps the narrator's paragraph and the
-- cold-start report. Additive only.
-- Applied via the Supabase MCP (apply_migration) on 2026-08-28.

alter table poi drop constraint poi_trust_check;
alter table poi add constraint poi_trust_check
  check (trust in ('verified', 'draft', 'ai_generated'));

alter table doc_chunk add column theme text;
alter table doc_chunk add column tier int check (tier in (2, 5, 10));

create table city_centre (
  name text primary key,
  lat double precision not null,
  lng double precision not null,
  name_kn text,
  source text not null default 'ai_generated'
);
insert into city_centre (name, lat, lng, source)
select city, avg(lat), avg(lng), 'poi_average' from poi group by city
on conflict (name) do nothing;

alter table trip add column narration text;
alter table trip add column cold_start jsonb;
