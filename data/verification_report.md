# POI verification report — 2026-08-27

Scope: the 10 highest-popularity POIs in Mysuru and the 10 in Hampi (ties broken by seed order), checked with Tavily web search within the 15-minute cap (about 8 minutes of searching, estimated). Fields checked: `opens`, `closes`, `closed_on`, `entry_fee_inr`. Each verified row now carries `source_url`, `last_verified=2026-08-27`, `trust=verified`. The other 92 POIs remain `trust=draft`.

Method caveats:
- Fees change without notice and the web is full of stale copies; where sources disagreed I took the most recent-looking or most official page, cited that one, and listed the others below.
- One record cites one URL. Where hours and fee came from different pages, the cited page is the one for hours and the fee page is named in the notes.
- Nothing was invented: a value that no page supported was left as it was and flagged "estimated".

## Mysuru (10)

| POI | Result | Notes / contradictions |
|---|---|---|
| Mysore Palace | fee 100 -> **120**; 10:00-17:30 daily confirmed | Sources disagree: mysore.nic.in and explorebees still say Rs 50 (stale); mysoretourism.org.in and groowynd say Rs 120; inmysore.com says Rs 150. Took 120. |
| Chamundeshwari Temple | confirmed free, 07:30-21:00 | Breaks 14:00-15:30 and 18:00-19:30 (mysoretourism.org.in); official e-ticket portal exists for paid sevas. |
| Brindavan Gardens (KRS Dam) | fee 50 -> **100**; 06:30-20:00 confirmed | Hours from karnatakatourism.org (official). Fee Rs 100 per mysoretourism.org.in; explorebees says Rs 15 (stale). Fountain 18:30-19:30 weekdays, to 20:00 weekends. |
| Mysore Zoo | fee 100 -> **150** (weekday); 08:30-17:30, closed Tue confirmed | explorebees (Aug 2026) lists Rs 150 weekday / Rs 180 weekend; mysoretourism.org.in says Rs 120. Weekend price stored as a note, flagged estimated. |
| Somanathapura Chennakesava Temple | opens 08:30 -> **09:00**; fee 25 -> **20** | kiomoi.com: 09:00-17:30, Rs 20 (online ASI price). explorebees and a Facebook post say Rs 5 (stale). Counter price may be Rs 25 (estimated). |
| Ranganathittu Bird Sanctuary | fee 70 -> **75**; hours -> **09:30-17:30** | mysoretourism.org.in: Rs 75, 09:30-17:30, boat Rs 100. gotirupati.com says 09:00-18:00; a Facebook answer says the counter opens 06:30. |
| Daria Daulat Bagh, Srirangapatna | **Friday closure removed**; fee 25 -> **20**; 09:00-17:00 confirmed | mysoretourism.org.in and oneshorttrip.com both say open all days. Fee Rs 20 (online ASI price); groowynd says Rs 15 (older). |
| Sri Ranganathaswamy Temple, Srirangapatna | opens 07:30 -> **06:00**; closes 20:00 confirmed; free | karnatakatourism.org (official): 06:00-13:00 and 16:00-20:00. mysoretourism.org.in says 07:00-13:30 and 16:00-20:30. |
| St. Philomena's Cathedral | confirmed free, 05:00-18:00 | mysoretourism.org.in; parish site lists mass timings only. |
| Jaganmohan Palace Art Gallery | opens 08:30 -> **10:00**; fee 20 confirmed | mysore.nic.in (government): 10:00-17:30 all days, Rs 20. mysoretourism.org.in says Rs 60 and 08:30-17:00 (contradiction, not adopted). |

## Hampi (10)

| POI | Result | Notes / contradictions |
|---|---|---|
| Virupaksha Temple | closes 20:30 -> **21:00**; free confirmed | hampitourism.co.in: 06:00-13:00 and 17:00-21:00, special darshan Rs 25. hampi.in says "sunrise to sunset, Rs 2" (stale). |
| Vittala Temple and Stone Chariot | closes 17:30 -> **18:00**; Rs 40 confirmed | hampitourism.co.in: 08:30-18:00, Rs 40 Indians / Rs 600 foreigners. hampi.in says Rs 30 and 06:00-18:00 (stale). staybook says 08:30-17:30. |
| Lotus Mahal (Zenana Enclosure) | Rs 40 and 08:30-17:30 confirmed (same-day ticket with Vittala) | staybook.in and hampi.in: one ASI ticket covers Vittala, Lotus Mahal, Elephant Stables. trawell.in and myholidayhappiness list Rs 10 and 08:00-18:00 (older separate ticket). |
| Elephant Stables | as Lotus Mahal | hampitourism.co.in also lists Rs 10; treated as the older separate-ticket price. |
| Hazara Rama Temple | hours 08:30-17:30 -> **06:00-18:00**; free | Three sources agree (hampitourism.co.in, tripnetra, myholidayhappiness). |
| Royal Enclosure and Mahanavami Dibba | hours 08:30-17:30 -> **06:00-18:00**; free | hampitourism.co.in (Feb 2026); myholidayhappiness says 08:00-18:00. |
| Lakshmi Narasimha Statue | closes 18:30 -> **18:00**; free | hampitourism.co.in (Feb 2026), NDTV, myholidayhappiness agree on 06:00-18:00. |
| Hemakuta Hill Temples | closes 18:30 -> **18:00**; free | incredibleindia.gov.in (official): 06:00-18:00; hampitourism says sunrise to sunset. |
| Matanga Hill | opens 05:30 -> **06:00**; free | Single source (myholidayhappiness). Sunrise hikers do start earlier in practice; hours are advisory. |
| Anjanadri Hill (Anjaneya Hill) | closes 18:30 -> **18:00**; free; ~575 steps confirmed | trawell.in; Facebook/Instagram posts say ~600 steps. |

## Summary

- Verified: 20 (10 Mysuru, 10 Hampi). Draft: 92.
- Corrections applied: 16 of 20 rows changed at least one field; the notable contradictions were Mysore Palace (Rs 50 / 120 / 150 across sources), Mysore Zoo (Rs 120 vs 150/180), Brindavan Gardens (Rs 15 vs 100), and Daria Daulat Bagh (no Friday closure, contrary to the seed).
- Not verified this pass: everything in Bengaluru, Chikmagalur and Coorg, and the remaining Mysuru/Hampi rows. Their fees and hours are estimates.
