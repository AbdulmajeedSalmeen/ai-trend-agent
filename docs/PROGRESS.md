# Progress

**Last updated:** 2026-09-16 · **Tests on dev:** 33 passing (local and CI)
**Days left:** Integration 1 in 4 days (Sep 20) · demo-ready in 10 days (Sep 26)

Lead updates this file after every standup. If it is stale, nothing below is trustworthy.

## Next actions

1. **Ali (Stage 1):** push `hn_sample.json` and `github_sample.json` before tonight.
2. **Naif (Stage 2b):** push the six verdict-rule tests before tonight, marked `skip` with a stub module, so `dev` stays green.
3. **Lead:** start Stage 4, tests first.
4. **ABDULRHMAN:** add `run()` to stage 2a, and switch tests from `SimpleNamespace` to real `Signal`.

## Owners

| Area | Owner |
|---|---|
| Schema, runio, Stage 4, pipeline, repo | Abdulmajeed (Lead) |
| Stage 2a clustering | ABDULRHMAN |
| Stage 1 ingestion | Ali |
| Stage 2b verify + Stage 3 score | Naif |
| Website | Claude with Lead, after Integration 2 |

## Decisions made

- One agent with four specialised stages, not one agent per stage.
- No LLM inside the product. Hugging Face embeddings for clustering, LangGraph for orchestration.
- No Streamlit. A website is built after Integration 2.
- Everyone pushes directly to `dev`. `dev` merges to `main` only on integration days.
- `main` requires passing tests. No review requirement.
- The schema workshop was skipped; members read the contract on their own.

---

## Setup and GitHub

- [x] Repository `ai-trend-agent` with `main` and `dev`
- [x] CI runs pytest on every push
- [x] `main` protected: tests must pass, no force push
- [x] All four members accepted as collaborators
- [x] Old feature branches deleted, early `dev → main` PR #3 closed
- [ ] Each member adds their name to README (day-1 exercise)
- [ ] Every member has the full `requirements.txt` installed
  (Lead is missing `langgraph`, `requests`, `python-dotenv`, `sentence-transformers`)
- [x] Stage owners confirmed: Ali = Stage 1, Naif = Stage 2b + 3
- [ ] Ali has a GitHub token in `.env`

## Planning

- [x] `docs/plans/TEAM-PLAN.md` and one plan per member
- [x] Data contract written in TEAM-PLAN
- [x] `docs/PROGRESS.md` started
- [ ] Daily standup notes recorded here

## Shared contract — Lead

- [x] `src/schema.py`: Signal, Claim, Trend, Score, Recommendation, UTC guard — 10 tests
- [x] `src/runio.py`: `new_run_id`, `run_dir`, `save_artifact`, `load_artifact` — 6 tests
- [ ] Every member ran `python -m pytest` on their own machine after pulling

## Stage 1 — Ingestion — Ali

- [ ] Explore Hacker News and GitHub APIs by hand, save `hn_sample.json` and `github_sample.json`
- [ ] GitHub token created, stored in `.env`, never committed
- [ ] `parse_hn_hit` and `parse_release` with offline tests
- [ ] `fetch_hackernews` and `fetch_github_releases` with timeouts, rate-limit and `TRUNCATED` logging
- [ ] `stage1_ingest.run()` saves raw responses first, then `signals.json` through runio
- [ ] One real run with 100+ signals from both sources

## Stage 2a — Clustering — ABDULRHMAN

- [x] `signals_fixture.json` with 12 signals
- [x] `extract_version` keeps the full version and takes the first one
- [x] `signal_text` and `group_known_subjects`
- [x] `cluster_signals` with TF-IDF and agglomerative clustering
- [x] `make_claims`
- [x] `docs/TUNING.md` started
- [x] 16 tests
- [ ] `run()` that loads `signals.json` and saves `trends.json` through runio
- [ ] Tests use real `Signal` objects instead of `SimpleNamespace`
- [ ] Sep 21–22: Hugging Face embeddings, with a measured comparison against TF-IDF

## Stage 2b + 3 — Verify and score — Naif

- [ ] Six verdict-rule tests, written first and failing
- [ ] `find_evidence`, `verify_claim`, `run()`
- [ ] Test: same version, different subject, never confirms
- [ ] `match_chapter` against `fixtures/curriculum.json`
- [ ] `score_trend` with five dimensions, provenance, weights asserting to 1.0
- [ ] Five scoring tests
- [ ] Offline chain produces at least one `confirmed` and one `unverified` claim

## Stage 4 + pipeline — Lead

- [ ] Four decision-table tests, written first
- [ ] `decide_action`, `build_rationale`, `run()`
- [ ] `src/pipeline.py`: one command runs every stage (stubs allowed) — Sep 18
- [ ] LangGraph graph, with a test that the plain sequential path gives identical files — Sep 19

## Integration — whole team

- [ ] **Sep 20 — Integration 1:** one command runs all stages on fixture data; then merge `dev → main`
- [ ] Sep 21–22: live API data, Hugging Face embeddings, verdicts checked on real data
- [ ] **Sep 23 — Integration 2:** full live run, cached, containing both `confirmed` and `unverified`

## Website — Claude with Lead

- [ ] Sep 23–24: website reads the JSON files of one cached run

## Demo

- [ ] Demo run chosen on purpose, not the newest by default
- [ ] Sep 25: rehearsal 1, timed
- [ ] Sep 26: rehearsal 2, code freeze, offline fallback drill
- [ ] Prepared answers: why one agent and not many, why no LLM, what `unverified` means

## Standup log

Newest first.

### 2026-09-16
- Lead: `runio.py` done with 6 tests. Found and fixed an early `return` inside a loop that loaded only the first item.
- ABDULRHMAN: TF-IDF clustering and claim extraction pushed. Stage 2a is ahead of schedule.
- Naif, Ali: no stage code pushed yet.

### 2026-09-15
- Lead: `schema.py` with 10 tests pushed.
- ABDULRHMAN: fixture, version extraction, subject grouping pushed.
