# TRAVEL YANTRA — MAJOR PROJECT PHASE-2, REVIEW 1

**10-Minute Presentation Script | Slide-by-Slide Guide**
BMSIT&M | Dept. of Information Science & Engineering | AY 2026-27 | BCS705
Under the Guidance of: Prof. Shwetha T, Assistant Professor, Dept. of ISE
Team: Nithin G (1BY23IS140) | Pushkar Reddy S (1BY23IS167) | Rishab Paul (1BY23IS175) | Rohan Balu (1BY23IS177)

Every number in this script is in `docs/review1/numbers.md`, with the command it came from.
Written for a technical panel: each technical term is said once, followed by what it means in plain words.
Short sentences, the real mechanism, no metaphors.

---

## TIME BUDGET

| Block | Slides | Speaker | Time |
|---|---|---|---|
| Title, content, abstract | 1–3 | Nithin | 0:52 |
| Introduction, problem | 4–5 | Pushkar | 0:50 |
| Objectives | 6 | Rishab | 0:25 |
| Methodology: the solver, the checklist, the guide | 7–9 | Rohan | 1:40 |
| Hand-off to the live system | 10–12 | Rohan | 0:10 |
| **LIVE DEMONSTRATION** | (on screen) | Rohan | **2:00** |
| Results | 13–14 | Rishab | 1:04 |
| Status, publication, references, close | 15–17 | Pushkar, Nithin, Rohan | 0:55 |
| **Speaking total** | | | **5:56** |
| **Demo** | | | **2:00** |
| **Question and answer** | | | **2:00** |
| **Total** | | | **9:56** |

**Before you start.** Server running (`uv run uvicorn app.main:app --port 8080`), signed in as
`rohan@travelyantra.in`, `uv run python scripts/demo_seed.py` already run. Tab 1 on `/trips/new`.
Tab 2 on the Mysuru + Hampi doesn't-fit page. Tab 3 on the Mangalore plan. Sound on, volume at seventy.
The cue card at the end has the click order.

---

## SLIDE 1 — Title
**Speaker: Nithin G | 25 seconds**

[All four standing. Nithin speaks.]

Good morning, respected faculty and panel members. We are Nithin, Pushkar, Rishab and Rohan, from
Information Science and Engineering, guided by Prof. Shwetha T.

Our project is Travel Yantra. It plans a trip for you and then walks beside you as a guide.

Planning a trip in India means twelve browser tabs. And a chatbot's answer can be confidently wrong about
when a place closes. That is the problem we set out to fix.

---

## SLIDE 2 — Content
**Speaker: Nithin G | 5 seconds**

This is our order. Please hold us to the results section. That is where we test our own claims.

---

## SLIDE 3 — Abstract
**Speaker: Nithin G | 22 seconds**

In one paragraph. The trip plan is worked out by a deterministic solver. That is ordinary code following fixed
rules, so the same request always gives the same plan. The large language model, the LLM, does three things
around it. It reads what you type. It drafts data for a city we have never seen. And it writes the finished
plan up and reads the guide aloud.

Here is the one claim we want to land today. The model handles language. Our own code does the scheduling.
We built it that way because it is measurably more reliable, and we can show you the working.

---

## SLIDE 4 — Introduction
**Speaker: Pushkar Reddy S | 22 seconds**

Thank you, Nithin. Phase 1 gave us the problem, twenty-two papers and six measurable objectives. Phase 2 is
building it.

One point of scope. The planner has nothing in it that is specific to one state. We demonstrate it on
Karnataka because that is where we have checked our data by hand. Ask it for a city we have never seen, and it
performs a cold start: the model drafts the places for that city, and every one is labelled unverified. You
will see that today.

---

## SLIDE 5 — Problem Statement
**Speaker: Pushkar Reddy S | 28 seconds**

Let me be concrete. A three-day trip has to respect opening hours, weekly closing days, entry fees, road time,
a lunch break, a budget, and how far the oldest person can walk. In our field that is a constraint
satisfaction problem: a set of conditions that all have to hold at once, and fixing one can break another.

Booking sites each solve one slice and leave you to join them up. Chat models write fluent plans. But on the
published TravelPlanner benchmark, GPT-4 produced a plan that met every condition six times in a thousand.
And it will state an entry fee it has no way of knowing.

So the engineering problem is not "write an itinerary". It is: work the plan out against its conditions, and be
able to show how.

---

## SLIDE 6 — Objectives of the Work
**Speaker: Rishab Paul | 25 seconds**

Thank you, Pushkar. These are the objectives exactly as we wrote them in Phase 1. We did not rewrite them to
match what we finished.

Objective 1, AI-powered personalised itinerary generation. Day-by-day plans from your preferences, budget,
dates and who is travelling. Demonstrated today.

Objective 5, the virtual cultural tour guide, built on retrieval-augmented generation. RAG means the model can
only speak from paragraphs we have written and stored; it finds the relevant ones and speaks from those.
Demonstrated today as the feature we call Katha.

Objectives 2, 3 and 4 — five languages, WhatsApp and voice, live booking — are Review 2 work. We say so
again on the status slide.

---

## SLIDE 7 — Methodology
**Speaker: Rohan Balu | 45 seconds**

Thank you, Rishab. This slide is the heart of the project, so I will take a moment.

Eight stages, left to right. The orange boxes are the model. The blue boxes are our own code.

Stage one. You type what you want in your own words. The model reads that into a form, in JSON mode at
temperature zero — a strict machine-readable shape, with no creativity allowed. You check the form. Stage
two, the cold start. If you ask for a city we have never seen, the model drafts its places. Every one is
labelled unverified until a source confirms it.

Then our code takes over. It picks candidate places from your interests. It runs k-means clustering: it
groups the places by which part of the city they are in, so a day does not zig-zag across town. It orders
each day with a nearest-neighbour pass: always go to the closest place you have not seen yet. Then 2-opt: if
the route crosses itself, we reverse a section and the crossing disappears, and we repeat until nothing
improves. All of this under each place's opening hours.

Then a validator and a repair loop, on the next slide. Then one plain sentence per stop, from templates.
Only at the end does the model write the plan up and read the guide aloud.

Stages three to seven are ordinary code with a fixed random seed. The same request always gives the same plan.

---

## SLIDE 8 — Methodology (contd.): the validator and the repair loop
**Speaker: Rohan Balu | 30 seconds**

The validator is the contract. It is a checklist the plan has to pass before you ever see it. Is anything
closed that day. Does it fit the budget. Is there a gap for lunch. Does the day end when you asked.

When a check fails, the repair loop takes out one flexible stop and rebuilds only that day. The days on either
side do not move. A stop is hard or soft: a train will not wait for you, but lunch will. We protect the first
and move the second.

On the right is why we did it this way. Two benchmarks, two research groups, one finding. On TravelPlanner,
GPT-4 met every condition six times in a thousand. Hand the same conditions to a solver, as Hao and colleagues
did, and it passes ninety-three point nine percent. On ChinaTravel, adding a solver made the agent ten times
better. Those are their numbers, not ours. We are following a published result.

---

## SLIDE 9 — Methodology (contd.): Katha, the guide
**Speaker: Rohan Balu | 25 seconds**

A city Katha is a fixed portrait. What the city is, how it began, who ruled, what it feels like, what it
eats, what is worth your time. More minutes means more of the portrait, never more about the inside of one
monument. That lives in the Place Katha, one click deeper.

For a place, a day or a question, we retrieve. Every paragraph becomes an embedding: a list of numbers that
captures its meaning, so a question asked in Kannada lands near an answer written in English. Those vectors
live in Postgres with pgvector, our vector store. A second search matches exact words. Reciprocal rank fusion
merges the two rankings. Below a similarity of 0.81 with no exact match, the guide refuses.

After the model writes a paragraph, a groundedness check compares every date, number and name with the
source. If it added anything of its own, we throw it away and try again.

---

## SLIDES 10, 11, 12 — Demonstration of Project Execution
**Speaker: Rohan Balu | 10 seconds**

These are our screenshots, in the deck as evidence. I would rather show you the system running.

[Switch to the browser, tab 1.]

---

## LIVE DEMONSTRATION — 2 minutes
**Driver and speaker: Rohan Balu**

> Keep talking while things load. Every sentence below is short on purpose.

**1. [0:00–0:20] The form, tab 1 on `/trips/new`.**
[Paste the placeholder sentence into the top box. Click **Fill the form from this**. Point at the fields
that filled themselves: the two cities, three days, the four travellers, the budget, the train.]
> "This is the model reading what we wrote. We check it. It does not decide anything."

**2. [0:20–0:35] Make the plan.**
[Click **Make my plan**. Read the numbers as they appear.]
> "Twenty-seven candidates from a hundred and thirty-five places. Three clusters, one a day. Thirty-five
> kilometres in list order, brought down to thirty-one. Thirty-seven checks, all passed. Computed, not
> guessed."

**3. [0:35–0:50] The plan page.**
[Click **See your three plans**, then the recommended card. Point at **In a few words**.]
> "The model wrote this from the finished plan, and we checked every number and name in it against the
> plan. Under each day there is a getting-around line — a cab, estimated, shown but never counted."

**4. [0:50–1:05] As listed, as routed.**
[Click the **Day 2** tab. Click **As listed**, then **As routed**.]
> "Same four stops. In list order, ten and a half kilometres. Once we work out the route, six and a half.
> Same opening hours, same day."

**5. [1:05–1:20] One chat edit.**
[Click the quick chip **Make Day 2 lighter**. Wait for the reply. Point at the dashed line.]
> "One stop out of Day 2. Days 1 and 3 did not move, and the dashed line says so. We have a test that
> proves the other days are untouched."

**6. [1:20–1:40] Katha, in Kannada.**
[Top nav → **Katha** → **Listen** on the Mysuru row → **2 min** → **ಕನ್ನಡ** → **play**.]
> "A portrait of the city, told the same way every time, with a source under every paragraph. The voice is
> Sarvam, from our own cache, so this works with the WiFi off."

**7. [1:40–1:55] A city we never seeded — tab 3, the Mangalore plan.**
[Switch to tab 3. Point at the **AI-drafted · unverified** chips.]
> "We had never seen Mangalore. The model drafted twenty-three places in thirty-two seconds. Our own code
> still did the scheduling. Every drafted stop is labelled unverified until a source confirms it."

**8. [1:55–2:00] If time remains — tab 2, the doesn't-fit page.**
> "Two cities, one day. We refuse, we show the arithmetic, and we offer two plans that do fit."

[Switch back to the deck, slide 13.]

---

## SLIDE 13 — Experimental Setup, Results & Analysis
**Speaker: Rishab Paul | 32 seconds**

Thank you, Rohan. The setup is on the top line: Python and FastAPI against Postgres with pgvector, the models
through OpenRouter, embeddings computed locally, speech from Sarvam.

On the left, the data. A hundred and thirty-five places. Twenty of them we checked against live sources by
hand. Sixteen of those twenty were wrong before we checked them. Wrong fees, wrong closing days. That is the
strongest argument we have for checking rather than trusting. It is why ninety-two seeded places are labelled
estimated, and the twenty-three the model drafted are labelled unverified.

On the right, the planner. Thirty-five kilometres if you visit the stops in list order; thirty-one once we
work out the route. Day 2 alone: ten and a half against six and a half. Thirty-seven checks of thirty-seven.
Four milliseconds to build.

---

## SLIDE 14 — Experimental Setup, Results & Analysis (contd.)
**Speaker: Rishab Paul | 32 seconds**

Retrieval, and here we want to be straight with the panel.

The measure is Recall at five: was the right paragraph among the top five results. For twenty-six questions
in thirty, it was. Dense retrieval, the meaning-based search, and hybrid retrieval, meaning plus exact words,
score exactly the same. Hybrid, which we built second, takes nearly twice as long. It tied. It did not win.

We kept it for one measured reason. On exact names the word search is as good as the meaning search at less
than half the time, and that is how a traveller looks for a monument. And the meaning search carries Kannada,
where an English word index has almost nothing to match: five in six against one in six.

One more. Our score fell when we merged our hand-written paragraphs in. We re-measured this morning after
adding the city portraits. Recall did not move; the mean reciprocal rank, which rewards the right answer
sitting first, dipped from 0.77 to 0.75. We report it as it is. Seventeen of eighteen narrated segments
passed the groundedness check. The refusal test is six of six. A hundred and forty-four automated tests pass.

---

## SLIDE 15 — Project Status, Conclusion
**Speaker: Pushkar Reddy S | 22 seconds**

Thank you, Rishab. Completed: the intake that reads your words, the cold start for a city we have never seen,
the planner, retrieval, the three kinds of Katha, the fact-checked narration, cached speech, one-day chat
repair, and the web app on real map tiles. In progress: verifying the model-drafted places, and counting the
getting-around cost against the budget. Not started, and named: Objectives 2, 3 and 4, and a dedicated vector
database once the corpus grows to five languages. That is Review 2.

The limits are on the slide in plain words. Drafted places are unverified and labelled. The getting-around
cost is an estimate we show but do not yet count. Routes are straight lines between stops. We are on localhost
today.

---

## SLIDE 16 — Publication
**Speaker: Nithin G | 18 seconds**

Our publication target is a benchmark we call IndiaTravel, modelled on ChinaTravel. The new part is the set of
conditions, because Indian ones have no counterpart yet: temple darshan windows, festival crowds, monsoon
roads, Jain food, and families with an elder and a child. Our planner and our labelled dataset would ship
alongside it. A Scopus-indexed venue, drafting after Review 2.

---

## SLIDE 17 — References
**Speaker: Nithin G | 5 seconds**

Nine references. Every one is a paper or a method that is running in the code.

---

## CLOSING STATEMENT
**Speaker: Rohan Balu | 10 seconds. All members present.**

The plan is computed, and it can show its working. The guide speaks only what a source supports, and refuses
when it has nothing. And where a measurement went against us, we put it on the slide. That is what makes the
rest believable. Thank you. We are open to questions.

---

# ANTICIPATED QUESTIONS

Ten the panel is most likely to ask, then four more technical ones. Answers are three or four spoken sentences.

**Q1. You call it AI, but you said the AI does not make the plan. So where is the AI?**
In four places. The model reads what you type into the form. It drafts places for a city we have never seen.
It writes the finished plan up and it writes every word the guide says. And the embedding model behind the
meaning-based search is a neural model too. The one thing it never does is choose your schedule. That is on
purpose.

**Q2. What happens if I ask for a city you don't have?**
The form tells you it has to learn the city first, about twenty seconds. The model drafts twenty to
twenty-five real places with their hours and fees. Our own code then plans the days from that draft. Every
drafted stop wears a label on screen: AI-drafted, unverified. It stays labelled until a source confirms it.

**Q3. How is your data not made up?**
Three levels, each labelled on screen. Verified means we checked it against a live source and dated it.
Draft means we seeded it and have not checked it yet; the screen says estimated. Model-drafted means the AI
wrote it; the screen says unverified. Sixteen of the first twenty we checked were wrong before we checked them.

**Q4. What if the model hallucinates?**
Every paragraph it writes is checked against the source it was given. Any date, number or name that is not in
the source fails the check. We throw the text away and try once more at temperature zero. If it fails again,
we speak the source paragraph itself, and the plan summary is hidden rather than shown. Seventeen of eighteen
segments passed.

**Q5. Why does it refuse instead of trying?**
Because a plan that collapses at three in the afternoon is worse than an honest no. When two cities do not fit
in a day, we show the road time leg by leg and the hours a day holds. Then we offer plans that do fit, one
click away. You can argue with the arithmetic, because it is on the screen.

**Q6. Is this a chat model with a wrapper?**
No, and the difference is measurable. A wrapper inherits the benchmark result: six plans in a thousand meeting
every condition. Our plan comes from our own solver and passes a checklist or is refused. Unplug the model and
you still get a routed, checked itinerary. You lose the storytelling, not the plan.

**Q7. Why do you not show the user any percentages?**
Because a percentage sounds like a promise we cannot keep. Eighty-seven percent confidence means nothing to
someone standing outside a palace. So the traveller sees words, comfortable or tight, and real quantities:
kilometres, rupees, the time the day ends. Percentages stay in our engineering telemetry.

**Q8. How is this different from MakeMyTrip?**
MakeMyTrip is very good at booking, and we are not competing there. It will not arrange your Tuesday around
the zoo being shut on Tuesdays and your mother's knees. It will not tell you, in Kannada, why the palace has
the name it has. We decide what your day looks like. Booking is Objective 4, and it is Review 2.

**Q9. What remains for Review 2?**
Three objectives: the full five-language pipeline, the WhatsApp and voice channels, and live booking with
real road routing. Around them: verifying the model-drafted places, counting the getting-around cost against
the budget, OpenStreetMap as the place source for new cities, and a dedicated vector database once the corpus
grows past a few thousand paragraphs in five languages.

**Q10. How did you evaluate it?**
Three separate checks. The planner is judged by its own validator: thirty-seven of thirty-seven on the demo
trip. Retrieval is judged on thirty written questions and ten name lookups, reporting Recall at five and mean
reciprocal rank, with six questions the library cannot answer that it must refuse. Narration is judged by the
groundedness check after every paragraph. A hundred and forty-four automated tests run in about twenty seconds.

**Q11. Why Postgres with pgvector, and not a dedicated vector database?**
Today the corpus is three hundred paragraphs, and pgvector keeps the vectors in the same database as the
places and the plans: one store, one backup, one query for the exact-word and meaning searches together. At
that size the meaning search answers in about seventy milliseconds. Our Review 2 plan is a dedicated vector
database, Qdrant or Milvus, once the five-language corpus grows to thousands of paragraphs and needs sharding
and filtering at scale. The retrieval code already sits behind one interface, so the swap is a data move,
not a rewrite.

**Q12. Is 2-opt optimal? Why not solve the routing exactly?**
It is not guaranteed optimal; it is a local improvement that removes every crossing. A day has at most six
stops, so an exact search would also be cheap. We chose 2-opt because the route also has to respect opening
hours, and 2-opt lets the validator and the repair loop keep control of that. On the demo trip the
nearest-neighbour route was already the best one, which is why our honest baseline is the list order.

**Q13. How do you handle Kannada and Hindi?**
Three ways. The embedding model is multilingual, so a Kannada question finds an English paragraph by meaning
without translating anything. The narrator writes in the script you choose, and the groundedness check reads
Indic digits as the same numbers. And speech is Sarvam, an Indian text-to-speech service, cached for the demo.
English and Kannada work end to end today; Hindi is wired but not tested end to end.

**Q14. What does it cost to run, and how do you keep the data current?**
The whole project's model spend to date is about six cents. A plan narration costs about a fifth of a cent.
A cold start for a new city costs about one cent. Data has a date on every verified row, and the interface says
estimated or unverified for everything else. Keeping it current is a verification pass, which is the same
process that corrected sixteen of the first twenty.

---

## IF THE DEMO BREAKS

Which steps need the network. The database is remote, so any new plan or Katha needs it. The model is
remote, so the form fill, the plan summary, a fresh narration and a first-time city need it. Cached speech and
the pages already open do not.

- **Step 1, the form fill, fails.** Say: "The model is not answering, so we fill it by hand." Fill the four
  fields yourself. Fallback picture: `04b-form-step1.png`.
- **Step 2, the plan, stalls.** Say: "The database is on a session pooler in Mumbai." If it does not come,
  switch to tab 3 or the picture `07b-building.png`, and read the numbers from it.
- **Step 3, no "In a few words".** It does not appear when the model is unreachable or fails its check. Say
  so: "The summary is hidden rather than shown unchecked." Picture: `09b-plan-routed.png`.
- **Step 4, tiles do not load.** The sketch appears in their place after four seconds. Say: "The map falls
  back to our own drawing; the kilometres are the same." Picture: `10b-plan-day2-listed.png`.
- **Step 5, the chat edit is slow.** It makes one model call to read the sentence. Say: "That is the one place
  a model sits in the loop, and it is reading, not deciding." Picture: `12b-plan-chat-edit.png`.
- **Step 6, no audio.** Say: "It falls back to the browser's own voice." Press play again. The English text is
  local. Picture: `17b-katha-city.png`.
- **Step 7, Mangalore.** The rows already exist, so no first-time drafting happens live. If tab 3 is gone, use
  the picture `09c-plan-mangalore.png`.
- **Step 8, the doesn't-fit page.** Tab 2 is pre-rendered. Picture: `19c-doesnt-fit.png`.
- **A panel member asks for a number you do not have.** Say you will check it rather than estimate. That is
  the whole posture of this review.

---

## CUE CARD (one page)

**Run.** `uv run uvicorn app.main:app --port 8080` in `C:\TravelYantra`. Then `uv run python scripts/demo_seed.py`.
**Login.** `http://127.0.0.1:8080/signin` → `rohan@travelyantra.in` → the demo password from `.env`.
**Tabs.** 1: `/trips/new`. 2: the Mysuru + Hampi doesn't-fit page. 3: the Mangalore plan.

**Click order.**
1. Tab 1 → paste the placeholder sentence → **Fill the form from this**.
2. **Make my plan** → read the numbers.
3. **See your three plans** → the recommended card → point at **In a few words**.
4. **Day 2** → **As listed** → **As routed**.
5. Quick chip **Make Day 2 lighter**.
6. **Katha** → Mysuru **Listen** → **2 min** → **ಕನ್ನಡ** → **play**.
7. Tab 3 → the **AI-drafted · unverified** chips.
8. Tab 2 → the arithmetic and the two alternatives.

**Three sentences to fall back on.**
- "The model handles language. Our own code does the scheduling. Everything the model writes is labelled or checked."
- "We would rather show an honest label than a confident wrong number."
- "I do not have that figure in front of me; we will check it rather than estimate."
