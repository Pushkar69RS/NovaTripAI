# TRAVEL YANTRA — MAJOR PROJECT PHASE-2, REVIEW 1

**10-Minute Presentation Script | Slide-by-Slide Guide**
BMSIT&M | Dept. of Information Science & Engineering | AY 2026-27 | BCS705
Under the Guidance of: Prof. Shwetha T, Assistant Professor, Dept. of ISE
Team: Nithin G (1BY23IS140) | Pushkar Reddy S (1BY23IS167) | Rishab Paul (1BY23IS175) | Rohan Balu (1BY23IS177)

---

## TIME BUDGET

| Block | Slides | Time |
|---|---|---|
| Opening and framing | 1–3 | 0:52 |
| Problem and objectives | 4–6 | 1:20 |
| Methodology — the central claim | 7–8 | 1:17 |
| Hand-off to the live system | 9–11 | 0:12 |
| **LIVE DEMONSTRATION** | (on screen) | **2:00** |
| Results and analysis | 12–13 | 1:13 |
| Status, publication, close | 14–16 | 0:57 |
| **Speaking total** | | **5:51** |
| **Demo** | | **2:00** |
| **Question and answer** | | **2:00** |
| **Total** | | **9:51** |

**Before you start.** Server running on `127.0.0.1:8000`. Signed in as
`rohan@travelyantra.in`. `uv run python scripts/demo_seed.py` has been run.
Browser tab 1 on `/trips/new`. **Browser tab 2 already open on the Mysuru +
Hampi verdict page** — do not build that one live, it costs fifteen seconds you
do not have. Sound on, volume at about seventy percent.

---

## SLIDE 1 — Title
**Speaker: Nithin G | 25 seconds**

[All four team members standing. Nithin speaks.]

Good morning, respected faculty and panel members. We are a team of four from
the Department of Information Science and Engineering — Nithin G, Pushkar Reddy
S, Rishab Paul and Rohan Balu — working under the guidance of Prof. Shwetha T.

Our project is Travel Yantra: an AI-based personalised travel itinerary planner
and virtual tour guide with multilingual support.

In Review 1 of Phase 1 we told you what we intended to build. Today we are going
to show you what we have built, and we are going to show you the measurements —
including the one that did not go our way.

---

## SLIDE 2 — Content
**Speaker: Nithin G | 5 seconds**

This is the order we will follow. The section we would like you to hold us to is
Experimental Setup and Results, because that is where the claims are tested.

---

## SLIDE 3 — Abstract
**Speaker: Nithin G | 22 seconds**

In one paragraph: planning a trip in India today means assembling it by hand
across four or five platforms, almost all of them English-first. We have built a
system where the itinerary is computed by our own solver against real
constraints, and the AI is used only for language — understanding what you ask,
and telling you the story once the plan is settled.

Two of our six objectives are demonstrated today in working software.

---

## SLIDE 4 — Introduction
**Speaker: Pushkar Reddy S | 22 seconds**

Thank you, Nithin. Phase 1 gave us the problem, twenty-two papers of literature,
and six measurable objectives. Phase 2 is implementation.

One point of scope, stated up front so there is no confusion later. The planner
is an India-wide architecture — there is nothing in the solver that is specific
to one state. We demonstrate it on Karnataka because that is where our verified
data currently exists. The cultural guide is scoped to Karnataka, because every
paragraph it can speak has to be written and sourced first.

---

## SLIDE 5 — Problem Statement
**Speaker: Pushkar Reddy S | 30 seconds**

Let me be concrete about what makes this hard. A three-day trip has to reconcile
opening hours, weekly closing days, entry fees, road time, a midday meal, a
budget, and how far the oldest person in the group can walk. These are hard
constraints and they interact — you fix one and you break another.

Booking platforms each solve one slice and leave you to be the integration
layer. General chat models are fluent, but the published benchmark says they
pass under one percent of multi-constraint plans, and they will state an entry
fee they have no way of knowing.

So the engineering problem is not "generate an itinerary". It is: compute an
itinerary against its constraints, and be able to show the working.

---

## SLIDE 6 — Objectives of the Work
**Speaker: Rishab Paul | 28 seconds**

Thank you, Pushkar. These are the objectives exactly as they were written in our
Phase 1 report — we have not rewritten them to match what we managed to finish.

Objective 1, AI-Powered Personalised Itinerary Generation: a system that
generates day-by-day itineraries from user preferences, budget, dates and group
composition. Demonstrated today.

Objective 5, Virtual Cultural Tour Guide: a Retrieval-Augmented Generation based
interactive guide for history, food and cultural significance. Demonstrated
today, as the feature we call Katha.

Objectives 2, 3 and 4 — the full five-language pipeline, the WhatsApp and voice
channels, and live booking — are Review 2 work, and we will say so again on the
status slide rather than blur it.

---

## SLIDE 7 — Methodology
**Speaker: Rohan Balu | 45 seconds**

Thank you, Rishab. This slide is the central claim of the project, so I will
spend a moment on it.

The language model parses what the traveller writes, and narrates what has
already been decided. The itinerary itself is computed by our own deterministic
solver.

Following the boxes: a structured intake form; candidate selection using SQL,
your interest tags and a small knowledge graph of which places pair well
together; k-means clustering to group places into days by geography; then
nearest-neighbour ordering followed by 2-opt, under each place's opening-hour
window; then a validator; then a repair loop; then plain-sentence reasons from
templates.

Seven of those eight stages are ordinary code with a fixed random seed. The same
request always produces the same plan. Only the last box — narration — is the
model, and only after every decision has been made.

---

## SLIDE 8 — Methodology (contd.)
**Speaker: Rohan Balu | 32 seconds**

The validator is the contract. Six checks per day: opening hours, closing days,
advisory closures, the time the day has to end by, a midday meal, and the share
of the day spent in transit — plus the budget across the whole trip.

If a check fails, the repair loop drops the lowest-scoring flexible stop of the
least-repaired day and rebuilds that one day. The fixed-time anchor — the palace
slot — is never dropped. Every other day is left byte-for-byte identical.

On the right is why we did it this way rather than trusting the model. The
TravelPlanner benchmark measured a single model at about one percent. ChinaTravel
measured a model paired with a solver at about ninety-seven. Those are their
numbers, not ours. We are following a published finding, not guessing.

---

## SLIDES 9, 10, 11 — Demonstration of Project Execution
**Speaker: Rohan Balu | 12 seconds**

These three slides are our screenshots, and they are in the deck as evidence.
Rather than read them to you, I would like to show you the system running.

[Switch to browser, tab 1.]

---

## LIVE DEMONSTRATION — 2 minutes
**Driver and speaker: Rohan Balu**

> Keep talking while things load. If anything stalls for more than three
> seconds, say "the database is on a session pooler in Mumbai" and move on.

**[0:00–0:18] The form — tab 1, already on `/trips/new`**
> Three steps. Where and when; who is going; money and tastes.
- Click **Next: who's going**.
- Say: "This is the step that matters. Two adults, one elder, one child. The
  moment there is an elder in the party, the planner changes what it is willing
  to schedule and moves the day's end time earlier."
- Click **Next: money & tastes**. Say: "Eighteen thousand rupees, heritage and
  food, and a note in plain English — *Amma tires by evening.*"

**[0:18–0:38] The interstitial**
- Click **Make my plan**.
- Read the numbers off the screen as they appear: "Twenty-seven candidates out
  of a hundred and twelve places. Three clusters, one per day. Thirty-four point
  nine eight kilometres as listed, brought down to thirty point nine as routed.
  Thirty-seven of thirty-seven checks passed. Three repairs."
- Say the last line: "**The plan is computed, not guessed.** Eleven
  milliseconds, and no AI in this part."

**[0:38–0:50] Three plans**
- Click **See your three plans**.
- Say: "Three, not thirty. Each one is a different scoring variant taken all the
  way through the solver, so each shows its real entry-fee total and whether it
  came out comfortable or tight."
- Click the **recommended** card.

**[0:50–1:12] The plan, and the honest map**
- Click the **Day 2** tab.
- Say: "The rail on the right is the day with real arrival times, travel legs
  and the reason each stop sits where it does. The filled pin on the map is the
  fixed-time stop."
- Click **As listed**. Say: "This is the same stops visited in list order — what
  an itinerary that never routes gives you. **Ten point five three kilometres.**"
- Click **As routed**. Say: "**Six point four five.** Same stops, same day, same
  opening hours."

**[1:12–1:24] The trace**
- Click **How this day was put together**.
- Say: "Everything the solver did for this day, on screen. We are not asking you
  to take the number on trust — the working is in the interface."
- Close it.

**[1:24–1:42] One chat edit**
- Click the quick chip **Make Day 2 lighter**.
- Wait for the reply. Point at the dashed line.
- Say: "**Day 2 rebuilt. Days 1 and 3 untouched.** That is not a claim in the
  copy — the other two days are the same objects in memory, and we have a test
  that asserts they are byte-for-byte identical after an edit."

**[1:42–1:56] Katha, in Kannada**
- Top nav → **Katha** → search **Mysuru** → **Listen** on the city row.
- Set **5 min**, **Quick**, then click **ಕನ್ನಡ**.
- Press **play**.
- Say over the audio: "This is the second objective. Every segment is typed —
  hook, story, fact — and every one carries the source it was built from. A
  legend is labelled as a legend. And the voice is Sarvam, served from our own
  cache, so this works with the WiFi off."

**[1:56–2:00] When it does not fit — switch to tab 2**
- Say: "One last thing, and it is the one we are most pleased with. Mysuru and
  Hampi in a single day. We do not build you a bad plan — we refuse, we show the
  arithmetic, and we offer three alternatives you can build with one click."

[Switch back to the deck, slide 12.]

---

## SLIDE 12 — Experimental Setup, Results & Analysis
**Speaker: Rishab Paul | 38 seconds**

Thank you, Rohan. The setup is on the top line: Python and FastAPI against
Postgres with pgvector, embeddings computed locally, speech from Sarvam.

On the left, the data. A hundred and twelve places. Twenty of them we verified
against live sources — and sixteen of those twenty were wrong before we checked
them. Wrong fees, wrong closing days. That single ratio is the strongest
argument we can make for verifying rather than trusting, and it is why
ninety-two places that we have not yet verified are labelled as estimated in the
interface rather than quietly presented as fact.

On the right, the planner. Thirty-four point nine eight kilometres as listed
against thirty point nine as routed; Day 2 alone, ten point five three against
six point four five. Thirty-seven of thirty-seven constraint checks. A three
millisecond build.

---

## SLIDE 13 — Experimental Setup, Results & Analysis (contd.)
**Speaker: Rishab Paul | 35 seconds**

Retrieval, and this is where I want to be straight with the panel.

Dense retrieval gets Recall-at-five of nought point nine three three. Hybrid
retrieval, which is the more sophisticated method and the one we built second,
gets exactly the same — nought point nine three three — at twice the latency.
**Hybrid tied. It did not win.**

We kept it for one measured reason: lexical retrieval is perfect on exact proper
nouns, an MRR of one point zero on name lookups, and that is how a traveller
actually searches for a monument. And dense retrieval carries Kannada, where the
English index has almost nothing to match — nought point eight three against
nought point three three.

One more. Our Recall-at-five fell from nought point nine three three to nought
point eight six seven after we merged our hand-written corpus in. We did not
tune it back up. Presenting a measurement that went against us is, we think, the
point of having measurements at all.

Fourteen of fourteen narration segments passed the groundedness check, the
refusal gate is six of six, and a hundred and one automated tests pass.

---

## SLIDE 14 — Project Status, Conclusion
**Speaker: Pushkar Reddy S | 22 seconds**

Thank you, Rishab. Completed: the database, the planner, retrieval, the Katha
builder, narration, speech, chat repair, the web application and the evaluation
harness. In progress: corpus breadth beyond five regions, and code review. Not
started, and honestly named: Objectives 2, 3 and 4 — the full five languages,
WhatsApp and voice, and live booking. That is Review 2.

The known limits are on the slide in plain words: ninety-two places still
unverified; Coorg has one midday food stop in our data, so a long Coorg day
trips our own meal-gap rule; the map draws straight segments, not road geometry;
and we are on localhost today.

---

## SLIDE 15 — Publication
**Speaker: Nithin G | 20 seconds**

Our publication target is a benchmark we are calling IndiaTravel — the first
India-specific benchmark for travel-planning AI agents, modelled on ChinaTravel
from ICLR 2026.

The novelty is the constraint set, because Indian constraints have no
counterpart in the existing benchmarks: temple darshan windows and midday
closures, festival crowding, monsoon access to hill roads, Jain food, and
multi-generational parties. Our planner and our verified dataset are the
reference implementation it would ship alongside. Scopus-indexed venue, drafting
after Review 2.

---

## SLIDE 16 — References
**Speaker: Nithin G | 5 seconds**

Ten references in IEEE format. Every one of them is a paper or an algorithm that
is actually running in the code — not a reading list.

---

## CLOSING STATEMENT
**Speaker: Rohan Balu | 10 seconds. All members present.**

To summarise: the plan is computed and it can show its working; the guide speaks
only what a source supports, and refuses when it has nothing; and where we
measured something that went against us, we have put it on the slide.

Thank you. We are open to questions.

---

# ANTICIPATED QUESTIONS

**Q1. What did you actually build, and what did the LLM do?**
We built the solver — candidate selection, clustering, routing, the validator
and the repair loop — and that is what produces the itinerary. The model does
two jobs only: it turns a sentence like "make Day 2 lighter" into a strict JSON
instruction, and it narrates a plan that has already been decided. It never
picks a stop, a time or an order. If it cannot parse a message it asks one
clarifying question instead of guessing.

**Q2. How do you know your data is correct?**
We do not, for all of it, and we say so. Twenty of a hundred and twelve places
were verified against live sources, each one citing exactly one URL and a
verification date. Sixteen of those twenty needed correcting. The other
ninety-two are marked as draft and the interface labels them as estimated. We
would rather show you an honest label than a confident wrong number.

**Q3. What if the model hallucinates?**
There is a check after every generation. We take the narrated text and compare
it against the paragraphs the model was given: any year, any number, and in
English any proper name that is not in the source fails. On a failure we retry
at temperature zero, and if it fails again we discard the model's text entirely
and speak the corpus paragraph itself. Fourteen of fourteen segments passed for
this demo. It is a fact-check, not a hope.

**Q4. Is this just ChatGPT with a wrapper?**
No, and the difference is measurable. A wrapper would inherit the one percent
pass rate from the TravelPlanner benchmark. Our itinerary comes out of a solver
that checks thirty-seven constraints and either passes them or refuses the
request. You can unplug our model entirely and still get a valid, routed,
constraint-checked itinerary — you would just lose the storytelling.

**Q5. Why do you not show the user any percentages?**
Because a percentage sounds like a promise we cannot keep. "Eighty-seven percent
confidence" means nothing to someone standing outside a palace. So the traveller
sees words — comfortable or tight — and actual quantities: kilometres, rupees,
the time the day ends. Percentages stay in the engineering telemetry where they
belong, and you can see them in the trace drawer.

**Q6. What happens when the plan is impossible?**
It refuses, and you saw it. Mysuru and Hampi in one day comes back as a verdict
rather than a plan: it shows the road time leg by leg, the twelve hours a day
actually contains, and the arithmetic that does not close. Then it offers three
alternatives you can build with one click. A system that always returns
something is a system that will happily hand you a day that dies at 3 pm.

**Q7. How is this different from MakeMyTrip?**
MakeMyTrip is very good at booking, and we are not competing with it there.
MakeMyTrip will not sequence your Tuesday around the fact that the zoo is closed
on Tuesdays and your mother cannot manage a thousand steps. It also will not
tell you, in Kannada, why the palace has a Kannada name. We are the layer that
decides what your day looks like; booking is Objective 4, and it is Review 2
work.

**Q8. What remains for Review 2?**
Three objectives. The full five-language pipeline — English and Kannada work
today, Hindi is wired but not tested end to end. The WhatsApp and voice
channels. And live booking and routing APIs, which will also replace our
straight-line map segments with real road geometry. Plus corpus breadth beyond
the five regions we currently cover.

**Q9. How did you evaluate it?**
Three separate harnesses. The planner is evaluated by its own validator —
thirty-seven checks, and the as-listed against as-routed comparison. Retrieval is
evaluated on thirty written questions plus ten name lookups, reporting
Recall-at-five and MRR, with a refusal gate of six questions the corpus cannot
answer. Narration is evaluated by the groundedness post-check. All of it is
reproducible, and a hundred and one automated tests run in about fifteen
seconds.

**Q10. Can it scale beyond Karnataka?**
The planner already does — there is nothing state-specific in the solver; it
needs rows in a table, so a new city is a data task, not a code task. The guide
is the harder half, because every paragraph has to be written and sourced before
it can be spoken. That is deliberate: it is exactly the constraint that stops it
inventing history about a place it has never read about.

---

## IF SOMETHING BREAKS

- **The network drops.** Keep going. Fonts, styling and the demo audio are all
  served locally. Only the database is remote — if it stalls, switch to tab 2,
  which is already rendered.
- **The chat edit is slow.** It makes one model call to parse the sentence.
  Say so out loud: "that is the one place a model sits in the loop, and it is
  parsing, not deciding."
- **Audio does not play.** Say: "it falls back to the browser's own voice" and
  press play again — that fallback is a real feature, not an excuse.
- **A panel member asks for a number you do not have.** Say you will check it
  rather than estimate. That is the whole posture of this review.
