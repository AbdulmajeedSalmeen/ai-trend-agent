# Progress

**Last updated:** 2026-09-26 · **Tests:** 432 passing · **Demo:** Sep 26–27

The pipeline runs end to end, live, from a web app. A model reads, judges and writes;
rules still decide what counts as confirmed, and every recommendation now carries the reason
behind it: what the chapter teaches, which version it runs, and how far the release has moved.

## Next actions

1. **Lead:** push the day's work, then merge `dev` into `main` (it is ~50 commits behind).
2. **Everyone:** `pip install -r requirements.txt` and create a `.env` with `GROQ_API_KEY=...`
   and `MODEL_ORDER=groq-fast,groq`. Without a key the stages fall back to rules and say so.
3. **Everyone:** when a new week is published, drop its notebooks into `notebooks/<week n>/` and run
   `python -m src.curriculum`. That reads the pins and the unpinned installs straight out of the
   material, and checks every `langchain` import against the newest release on GitHub. The folder is gitignored; the course files never leave the machine.
4. **Whole team:** Sep 25–26, two timed rehearsals and one offline fallback drill. Read
   `docs/DEMO-QA.md` first; every answer in it is backed by the frozen run.

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
- **The agent decides like a school, not a changelog.** A version number is evidence, never
  the reason on its own. Impact comes from what the release notes say changed (breaking,
  deprecation, feature, fix, chore), not from how often a package ships. Market relevance
  comes from job posts in the "Ask HN: Who is hiring?" threads and from PyPI installs, kept
  apart, not from how much a tool is discussed. A new lesson needs employers asking for it.
- PyPI is a second tier-1 source, because it is the registry `pip install` actually reads.
  Two registries carrying the same version is `registry_match`, not `cross_source`: they are
  the same publisher, and passing that off as an independent check would be grading our own
  homework.
- An unbound install only asks for a rewrite when the chapter teaches that package or still
  calls something a release removed. Otherwise it is a dependency to pin. Without that
  distinction the run asked to rewrite C24 because pandas moved.
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

- A run collects ~486 signals: ~316 Hacker News, ~90 PyPI releases, 80 GitHub releases.
- The PyPI watchlist is the 53 packages the course notebooks install, read from the material.
- 37 subjects, 157 claims: 139 primary reports, 14 registry matches, 4 unverified,
  **0 cross-source**.
- 12 chapters to update, 4 packages with no chapter at all, across 11 of the 25 chapters.
- The model reads every discussion post that names a tracked package. **None has yet stated
  anything a release page could check.** That is why cross-source is zero — the community
  discusses tools, it does not report versions. The per-run count is in the log.
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
- [x] `src/sources/pypi.py` — PyPI as a second tier-1 source, watchlist read from the course
- [x] `src/trace.py` — every model call timed, counted and priced, with a budget and a breaker
- [x] `src/memory.py` — what this run asked for that earlier runs already asked for
- [x] `docs/FROM-THE-COURSE.md` — what we took from the bootcamp and what we left
- [x] Team names in README, and how to run everything after the move to `web/`
- [x] `docs/DEMO-QA.md` — the hard questions, each answered from the frozen run
- [x] Demo run frozen: `run_20260921T104824Z` now travels with the repo, so anyone can
      replay it offline

## Not done

- [ ] `dev` merged into `main`
- [ ] Decide whether the material review may be published. Until then it stays on this machine
- [ ] Two timed rehearsals, and the offline fallback drill
- [ ] Raise or refill the OpenAI spend limit; until then every run is rules only
- [ ] The evaluation suite: frozen cases, several repeats, pass^k, a release gate
- [ ] Optional: GitHub token per member (60 requests/hour without one)

## Standup log

### 2026-09-26
- The material review, the half that asks whether a notebook still teaches the right method:
  AI reviewers, Claude agents with web research led from the design session, read all 89
  notebooks and wrote `material_review/1`. The page says they are AI, never "a reviewer" alone.
  `src/review.py` holds the rules that decide what the page may say: the chapter comes from the
  curriculum, replace or retire needs a hard finding, a credential is counted and never
  located, and every count is computed from what travels.
- Measured, not judged: 4 notebooks are identical to another cell for cell (`copies` in
  `fixtures/curriculum.json`). They are retired and their findings counted once. Two reviewers
  had given one of them a different verdict and a different new lesson from its identical twin.
- Model shutdowns measured from the code cells against OpenAI's deprecations table, read today
  into `fixtures/model_retirements.json`, with the defaults of LangChain's `OpenAI()` and
  `ChatOpenAI()` read in the langchain-openai source at 1.6.6 and 0.3.35: 28 September reaches
  2 notebooks, 23 October 22. The reviewers had 6 and 25, plus 11 December for `gpt-5-mini`,
  but that row lists only dated snapshots and no notebook names one.
- 10 findings said removed for a model whose shutdown is still ahead: relabelled deprecated by
  rule. One replace verdict rested only on absences: lowered to revise.
- The review stays on this machine: the repo is public and the review describes SDA's material
  in detail. `fixtures/material_review.json` and `web/dist/site-material.html` are ignored; the
  served page carries the review, `python -m web.site --material` writes the local offline page.
- The 26 new lessons the reviewers proposed are measured like a concept (`src/lessons.py`): a
  model picks the name a job post would use, the rules keep it only if the lesson itself uses it,
  it is not a word every AI post carries (one lower-case word is noise: "retention" found 9
  posts, about keeping customers and users, none about agent memory), and a name the course already teaches speaks only when it is the lesson's
  subject. Hacker News counts it. 1 new lesson (MCP, 20 posts, the same count the concept check
  found on its own), 3 optional (prompt injection twice, Structured Outputs), 22 watched. The
  counts are saved in `fixtures/lesson_demand.json`, ignored with the review, and the decision is
  remade from them whenever the page is built.
- OpenAI answered the term pick (`gpt-4o-mini`): the key works again and `MODEL_ORDER` now
  starts with it.
- 432 tests, none touching a model or the network.

### 2026-09-25
- The 19 install counts pypistats had refused on Sep 22 are in, filled one request at a time.
  Replayed from that run's own files: no action changed.
- Then collected the demo run itself, the day before the demo: `run_20260925T191944Z`. 433
  signals, 38 subjects, 174 claims (143 primary, 27 registry, 0 cross, 4 unverified), install
  counts for all 38. Decisions: 6 chapter updates, 1 course-wide change, 2 new lessons, 2
  optional notebooks, 27 watched, plus MCP as a concept lesson. The writer kept 34 of 38.
- The import check and the concepts were read again the same day: still 85 lines in 39
  notebooks across 11 chapters, MCP still 20 job posts and 0 of 89 notebooks.
- Everything pushed, the design work with it.

### 2026-09-22
- The lead asked for what a teacher actually needs: not "a package moved", but what to change
  in the material itself. Measured the brief against the build: no recommendation carried the
  initial action plan it asks for, and two of its five actions were missing.
- `src/material.py` checks every `langchain` import in the 89 notebooks against the source of
  langchain 1.4.2, read file by file at its release tag, and finds where each missing name
  went the same way. 85 lines in 39 notebooks across 11 chapters; one C8 notebook breaks on
  today's install, the other 38 pin LangChain 0.3 and teach its agent API.
- The check corrected our own pattern table. It had flagged four removed APIs in C8; three
  were false: imported from `langchain_classic` where they still work, a longer class name
  (`LLMChainExtractor`), and a comment. The table no longer matches LangChain names, reads no
  comments, and matches whole names only.
- Every recommendation now carries a two or three step plan in English and Arabic
  (`src/plan.py`), and the two missing actions exist: "investigate a larger change" when one
  release reaches several chapters (langchain), and "add optional content" when a tool has
  some demand and something to teach (crewai, pydantic-ai).
- Frozen run redecided with no model and no network: 3 actions changed, the other 34 cards
  kept their reasons word for word. Each card now records whether the model or the rules
  wrote its English reason; 17 of 37 were the rules.
- A server stopped mid-run no longer leaves a lock that refuses every run after it.
- Concepts the course does not teach (`src/concepts.py`): the module lists of langchain and
  langgraph at the course's version and at the newest release, read at their tags. langchain
  1.4.2 added `langchain.mcp`; 20 job posts named MCP in three months, 0 of 89 notebooks
  mention it: a new lesson. Five other new modules are watched, their names too common to
  count in job posts.
- Every run had exactly 80 GitHub signals: 10 releases from each of 8 repos, 9 days of one and
  189 of another. GitHub and Hacker News now read the same 30 days as PyPI; the langchain
  monorepo went from 10 releases to 26 across 8 packages.
- The writer kept 8 of 37 sentences; the rest dropped the version, and one called optional
  content "a new chapter". The prompt now lists the facts that must appear and says what each
  action means. On the new run 4 were refused instead of 29.
- The brief's three missing factors are measured (`src/feasibility.py`): maturity from PyPI
  history, prerequisites from what the course teaches, difficulty from the lines to change.
  They score feasibility beside the priority, not inside it, and maturity gates the decision:
  langchain-typesafe, pre-releases only, went from "update C8" to watch.
- Frozen run replaced by `run_20260922T102800Z`. pypistats refused during collection; install
  counts were filled afterwards for 18 of 37 subjects, the rest left unmeasured for the day.

### 2026-09-21
- The lead asked the right question: would a school care about every langchain version, or
  about whether a change matters for lessons and for jobs? Measured it. The judge had been
  shown nothing but "version 1.4.2 was released" and rated 29 of 37 packages 2 out of 5 with
  nothing above 3; "market relevance" was a count of Hacker News posts; "impact" was how often
  a package shipped. Rebuilt all three.
- `src/changes.py` reads the release notes we had been throwing away and sorts every line; of
  2,933 lines, nine in ten are fixes or chores. `src/sources/market.py` counts job posts
  naming each tool over three months (about 1,200 posts) and reads PyPI installs.
- Decisions moved from 12 updates and 4 new lessons to 5 updates and 2 new lessons, each with
  a reason a teacher would accept. crewai (4 job posts) is no longer a new lesson; torch,
  pinned at 2.5.1 and still running, is no longer a rewrite; six packages with no notes at all
  are no longer rewrites on their version alone. langchain stays a rewrite: its notebooks call
  APIs 1.x removed.
- Frozen run moved to `run_20260921T104824Z`, which carries market data and a trace.

### 2026-09-20 (evening)
- PyPI joined as a second tier-1 source and the watchlist is now the 53 packages the course
  installs, read from the notebooks. Coverage went from 2 chapters to 11.
- The model works again, on Groq. Getting there took five fixes: Cloudflare refuses Python's
  default user agent, the configured Groq model did not exist on the account, a non-fatal
  failure returned instead of trying the next provider, a reasoning model bills its thinking
  against `max_tokens` and our ceilings were too small, and a 429 was read as prose so a
  rate-limit message that links to a billing page was taken for a spent account.
- First run where the model survived start to finish: 151 calls, 46k tokens, nothing halted,
  21 of 37 sentences written rather than fallen back.
- Warnings are now errors (`pytest.ini`), with the two starlette ones ignored by exact
  message. Our own code raises none.
- **The OpenAI key is refused (401) and its project is over its spend limit. Groq carries the
  run.** `MODEL_ORDER` in `.env` picks the chain and can exclude a provider without deleting
  its key.

### 2026-09-20 (afternoon)
- Read all 89 notebooks and 27 decks, weeks 1 to 6, and wrote down what came back into the
  project and what we refused: `docs/FROM-THE-COURSE.md`. Three things were built from it.
  An execution trace with cost and latency (`src/trace.py`), which caught on its first run
  that the OpenAI key had hit its spend limit: 170 calls, 170 failures, and every stage
  quietly falling back to rules. A token budget plus a circuit breaker, so a refused key is
  not retried 170 times; the same replay went from 3.5 minutes to 3 seconds. And memory
  between runs (`src/memory.py`), so a recommendation says whether it is new or has been
  asked for several runs running.
- The sentence the model writes is now also refused when it contradicts the verdict, not
  only when it drops the facts. The week 6 deck calls this the semantic success trap.
- **The OpenAI key is out of quota.** Runs still complete on rules and say so on the page.

### 2026-09-20
- Read the whole bootcamp back into the project. PyPI added as a second tier-1 source, with
  the watchlist derived from the 53 packages the notebooks install: coverage went from 2
  chapters to 11. Two bugs the wider watchlist exposed and we fixed: chapters were matched
  by text alone, so `pypdf` became "add a new lesson" when C8 already installs it; and every
  unbound dependency asked for a chapter rewrite.
- From week 6 of the course itself: the guardrail idea (allowlist, hard limits, a fallback
  that explains itself) and the evaluation vocabulary (grounded citations, stability across
  runs) now have names in our own design.

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
