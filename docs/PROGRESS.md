# Progress

**Last updated:** 2026-09-19 · **Tests:** 149 passing · **Demo:** Sep 26–27

The pipeline runs end to end, live, from a web app. A model reads, judges and writes;
rules still decide what counts as confirmed, and every recommendation now carries the reason
behind it: what the chapter teaches, which version it runs, and how far the release has moved.

## Next actions

1. **Lead:** push the day's work, then merge `dev` into `main` (it is ~50 commits behind).
2. **Lead:** add the team names to `README.md`.
3. **Everyone:** `pip install -r requirements.txt` (fastapi, uvicorn, httpx are new) and create a
   `.env` with `OPENAI_API_KEY=...` — without it the stages fall back to rules and say so.
4. **Everyone:** when a new week is published, drop its notebooks into `notebooks/<week n>/` and run
   `python -m src.curriculum`. That reads the pins, the unpinned installs and the old API calls
   straight out of the material. The folder is gitignored; the course files never leave the machine.
5. **Whole team:** Sep 23–24 pick the demo run and freeze it; Sep 25–26 rehearse twice.

## Owners

| Area | Owner |
|---|---|
| Schema, runio, versions, Stage 4, pipeline, server, site, repo | Abdulmajeed (Lead) |
| Stage 1 ingestion | Ali |
| Stage 2a clustering and claim extraction | ABDULRHMAN |
| Stage 2b verification + Stage 3 scoring | Naif |

## Decisions made

- One agent, five stages. Not one agent per stage: the stages have no open decisions to negotiate.
- The model reads, judges and writes. **The verification gate stays rules** — a claim is confirmed
  only when a tier-1 release states the same subject and the exact same version.
- A claim can never be confirmed by the document it was read from (`source_signal_id`).
  Evidence from a different document is `cross_source`; the release speaking about itself is
  `primary_report`.
- One trend per subject; versions are claims inside it, not separate trends.
- Chapters are matched from the curriculum text (tool names included), not a hand-written map.
- A recommendation must carry its reason. The action comes from the distance between the version a
  chapter runs and the newest confirmed release: a major or minor jump is worth rewriting, patch
  releases never are. When the chapter's version is not recorded, the agent says exactly that
  instead of asserting the chapter is stale, and falls back to how many releases landed after the
  chapter was last updated.
- The curriculum records what each chapter teaches (`teaches`) and what its notebooks install
  (`pins`, `installs_unpinned`, `legacy_api`), read from the notebooks themselves, so the gap is
  measured rather than asserted.
- A package installed with no version bound is its own verdict. The chapter has no guarantee at
  all: a student installs whatever is newest that day.
- An old API call found in a notebook is labelled as coming from our pattern table, never from
  confirmed evidence. The two are never mixed.
- The model writes the sentence, but it is refused when it drops the facts it was given - the
  version or the API name. The rules sentence is used instead, and the run log says so.
- The curriculum is the real SDA course, read from the LMS: 25 chapters, weeks 1–7.
- `dev` is the working branch; `main` only on integration days.
- No test may call a model or the network (`tests/conftest.py` disables the model).

## Measured facts to quote at the demo

- A run collects ~395 signals: ~315 Hacker News, ~80 GitHub releases.
- 17 subjects, ~82 claims, 80 primary reports, 2 unverified, **0 cross-source**.
- The model read 14 discussion posts that name a tracked package. **None stated anything a release
  page could check.** That is why cross-source is zero — the community discusses tools, it does not
  report versions.
- Educational value is judged per trend (1–5 with a reason) and recorded as `judged`, never `measured`.
- Four tracked packages are absent from the curriculum: anthropic-sdk-python, crewai, llama_index,
  pydantic-ai.
- **The C8 finding.** Eight notebooks teach document QA on LangChain. Seven install `langchain`
  with no version bound; one pins `langchain==0.0.352` and `openai==0.28`. The code calls
  `RetrievalQA`, `LLMChain`, `load_qa_chain` and `openai.ChatCompletion` - all gone in 1.x. A
  student running that notebook today installs langchain 1.4.2 and the material does not run.
- The rest of the course runs `langchain==0.3.*`, `langchain-openai==0.2.*`, `langgraph==0.2.*`:
  one major version behind every confirmed release in this run.
- 89 notebooks across six weeks were read; every one was placed in a chapter.

## Done

- [x] `src/schema.py` — five models, UTC guard, evidence fields
- [x] `src/runio.py` — run folders, typed save/load
- [x] `src/versions.py` — shared version extraction, pre-releases kept whole
- [x] Stage 1 ingestion (Ali) — Hacker News + GitHub, raw caching, monorepo subjects
- [x] Stage 2a clustering (ABDULRHMAN) — TF-IDF, subject inference, claims per version
- [x] Stage 2b verification (Naif) — tier-1 only, exact version, no self-confirmation
- [x] Stage 3 scoring (Naif) — chapter matching, five dimensions, weights assert to 1.0
- [x] Stage 4 recommendations (Lead) — decision table, rationale
- [x] `src/pipeline.py` — one command, `--run-id` replays a saved run with no network
- [x] `web/runner.py` — lock file, background thread, progress, GitHub budget check
- [x] `web/server.py` — FastAPI: runs list, payload, status, start run
- [x] `web/site.py` + template — bilingual dashboard, four sections, charts, offline export
- [x] `src/adapters/model.py` + `src/reading.py` — provider-agnostic model, three thinking points
- [x] `src/gap.py` + `src/pin.py` — version distance, staleness by date, and a way to record pins
- [x] `src/notebooks.py` + `src/curriculum.py` — read the course notebooks into the curriculum

## Not done

- [ ] `dev` merged into `main`
- [ ] Team names in README
- [ ] Demo run chosen and frozen
- [ ] Two timed rehearsals, and the offline fallback drill
- [ ] Prepared answers: why one agent, why the gate is rules, what `unverified` means
- [ ] Optional: GitHub token per member (60 requests/hour without one)

## Standup log

### 2026-09-19 (night)
- All 89 course notebooks read (weeks 1-6). The curriculum is no longer a list of topic names: it
  now carries what each chapter installs, what it leaves unpinned, and which removed APIs it still
  calls. Two new verdicts followed - `unpinned`, and a legacy-API flag kept separate from
  confirmed evidence - and the model's sentence is now refused when it drops the facts.

### 2026-09-19 (evening)
- The dashboard said "update chapter C8" with no reason, on three patch releases of the same
  minor line. Fixed at the root: the curriculum now records what a chapter teaches and the version
  it runs, `src/gap.py` measures the distance, and patch-only movement can no longer call for a
  rewrite. Every card shows that distance next to the sentence.

### 2026-09-19
- Lead: Stage 4, `--run-id` replay, FastAPI server, the bilingual site, the run experience,
  and the model layer. The NVIDIA key turned out unusable (most models 404, the one that answers
  takes 60s a call); switched to OpenAI via `.env`.
- ABDULRHMAN: multi-version claims with dedupe, plus a measured TF-IDF vs embeddings comparison
  in `docs/TUNING.md` — TF-IDF won on this data.
- Naif: Stage 3 scoring, and the shared version extractor in Stage 2b.
- Found and fixed: every claim was being confirmed by the document it came from; chapter matching
  was landing on the words "a" and "into".

### 2026-09-18
- Pipeline chained end to end for the first time; stages 1, 2a, 2b complete.

### 2026-09-16
- Schema and runio merged; CI green on every push.
