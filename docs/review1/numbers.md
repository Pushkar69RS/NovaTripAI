# Review-1 numbers — re-derived 2026-08-28, ~06:50 IST

Every figure on the results, methodology, demonstration and status slides comes
from this file and from nowhere else: `scripts/build_deck.py` parses the JSON
block at the end. Each number carries the command it came from; run it again
and the deck follows.

## 1. Gates
`uv run ruff check .` → All checks passed. `uv run ruff format --check .` → 61 files already formatted.
`uv run pytest -q` → **144 passed** in ~19 s.

## 2. Canonical demo trip
`uv run python scripts/demo_seed.py` (Bengaluru → Mysuru & Srirangapatna, 3 days from 14 Sep 2026,
2 adults 40-59 + 1 adult 60+ + 1 child 6-12, family, comfortable, ₹18,000, heritage + food, cabs):
`metrics: as listed 34.98 km | nearest-next 30.9 km | routed 30.9 km | repairs 3 | candidates 27 | checks 37/37 | build 4 ms`
Day 2 alone: 10.53 km as listed → 6.45 km as routed (`Day.naive_km` / `Day.route_km` on the stored plan).
Candidates are 27 of the 135 places in the table (`SELECT count(*) FROM poi`).

## 3. Retrieval — `uv run python scripts/eval_retrieval.py` (eval_run id 10, after the city layer)
354 chunks indexed (live + retired rows carry embeddings; retrieval reads only the 300 live ones).

| block | method | Recall@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|
| A: 30 written questions | dense only | 0.867 | 0.753 | 68.6 | 108.9 |
| A | lexical only | 0.600 | 0.473 | 57.4 | 60.6 |
| A | hybrid + RRF | 0.867 | 0.753 | 128.8 | 154.0 |
| B: 10 name lookups | dense only | 0.900 | 0.907 | 62.6 | 76.7 |
| B | lexical only | 0.900 | 0.783 | 28.0 | 54.7 |
| B | hybrid + RRF | 0.900 | 0.857 | 87.4 | 116.9 |

Recall@5 by language (dense / lexical / hybrid): English (21) 0.857 / 0.762 / 0.857; Kannada (6) 0.833 /
0.167 / 0.833; Hinglish (3) 1.000 / 0.333 / 1.000. Refusal gate: 6 of 6 unanswerable queries returned nothing.
Hybrid ties dense on both blocks; it does not beat it. Against the previous run (eval_run 9): Recall@5
unchanged, MRR 0.772 → 0.753, hybrid p50 110 → 129 ms — re-measured after the city layer was added.

## 4. Database — `mcp supabase execute_sql` on project puzbpzdamygjosugoeeb
poi by trust: verified 20, draft 92, ai_generated 23 (all Mangalore) → 135 places in 6 cities.
Of the 20 verified places, 16 were corrected by verification (data/verification_report.md, 27 Aug).
doc_chunk: 354 rows, 300 live, 54 retired; 82 live rows carry a theme (14 per hub × 5 + 12 for Mangalore);
23 live rows are legends; 12 live rows are ai_generated. city_centre: 6 rows (5 poi_average + Mangalore).
app_user: 4. Cities with a city layer: Bengaluru, Chikmagalur, Coorg, Hampi, Mysuru (14 each), Mangalore (12).

## 5. Cold start — `SELECT cold_start FROM trip WHERE cold_start IS NOT NULL`
1 city cold-started: Mangalore — 23 places drafted (all inserted), 12 Katha paragraphs, 32.0 s, $0.0092,
model latency 11.5 s for the places call (server log line `cold start Mangalore: ...`).

## 6. Narration fact-check — `uv run python scripts/warm_tts.py` (28 Aug, second run)
18 segments narrated (9 English + 9 Kannada for the 5-minute Mysuru city Katha): **17 passed** the check
(English 8 of 9, Kannada 9 of 9); 1 fell back to the corpus's own words. Audio: 345 s English, 453 s Kannada.
Plan narration on the walk-through trips: passed after one retry on the Mysuru & Hampi trip (cost $0.0016).

## 7. Screenshots — `ls docs/screenshots` (newest per screen; a b/c suffix beats the original)
01-landing, 02-signin, 03-home, 04b-form-step1 (the pasted sentence, filled), 05b-form-step2, 06b-form-step3,
07b-building, 07c-building-coldstart (the "Learning about Mangalore" stage), 08b-chooser, 09b-plan-routed
(with "In a few words" and the getting-around line), 09c-plan-mangalore (AI-drafted chips),
10-plan-day2-listed, 11-plan-day2-trace, 12b-plan-chat-edit, 13-katha-day, 14b-katha-place, 15-katha-home,
16-katha-search, 17b-katha-city (2 minutes, no type labels), 18-katha-playing, 19b-doesnt-fit, 20-saved.

## 8. Literature figures (verified with tavily on 28 Aug; attributed on the slide)
TravelPlanner (Xie et al., ICML 2024): GPT-4-Turbo final pass rate 0.6% (confirmed: paper, opensymbolic.ai,
liner.com summaries). Hao et al. (NAACL 2025), the same benchmark with an LLM writing the constraints for a
satisfiability solver: **93.9%** final pass rate on the test set, 93.3% on validation (confirmed: arXiv 2404.11891
abstract, the authors' project page, the MIT thesis) — the "~97%" that circulated is NOT the paper's figure and is
dropped. ChinaTravel (Shao et al., ICLR 2026): neuro-symbolic agents 37.0% constraint satisfaction on human
queries, "a 10x improvement over purely neural models" (confirmed: ICLR 2026 poster page, the LAMDA project page,
arXiv 2412.13682); the earlier "2.6%" for purely neural agents could not be confirmed and is dropped — the deck
says "about one tenth of that", which is the paper's own comparison.

```json
{
  "tests": 144,
  "demo": {"listed_km": 34.98, "nn_km": 30.9, "routed_km": 30.9, "day2_listed_km": 10.53, "day2_routed_km": 6.45,
           "repairs": 3, "candidates": 27, "places": 135, "checks_passed": 37, "checks_total": 37, "build_ms": 4},
  "retrieval": {
    "written": {"dense": [0.867, 0.753, 68.6], "lexical": [0.600, 0.473, 57.4], "hybrid": [0.867, 0.753, 128.8]},
    "lookups": {"dense": [0.900, 0.907, 62.6], "lexical": [0.900, 0.783, 28.0], "hybrid": [0.900, 0.857, 87.4]},
    "kannada": {"dense": 0.833, "lexical": 0.167, "hybrid": 0.833},
    "refusal": [6, 6], "previous_mrr": 0.772, "previous_p50": 110, "eval_run": 10
  },
  "db": {"poi_verified": 20, "poi_draft": 92, "poi_ai": 23, "poi_total": 135, "corrected_of_verified": 16,
         "chunks_live": 300, "chunks_themed": 82, "chunks_legend": 23, "chunks_ai": 12, "cities_with_layer": 6},
  "cold_start": {"cities": 1, "city": "Mangalore", "places": 23, "paragraphs": 12, "seconds": 32.0, "cost_usd": 0.0092},
  "narration": {"passed": 17, "total": 18},
  "literature": {"travelplanner_gpt4": 0.6, "travelplanner_solver": 93.9, "chinatravel_neurosymbolic": 37.0, "chinatravel_neural_ratio": 10}
}
```
