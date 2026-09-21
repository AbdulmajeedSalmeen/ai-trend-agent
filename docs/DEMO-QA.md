# Demo answers

Every number here comes from `run_20260921T104824Z`. Re-run `python -m src.pipeline --run-id
run_20260921T104824Z` and they come back the same, because replay never touches the network.

## The run, in numbers

| | |
|---|---|
| Signals collected | 483 - 315 Hacker News, 88 PyPI releases, 80 GitHub releases |
| Packages followed | 53, every one the course notebooks install |
| Subjects tracked | 37 |
| Checkable claims | 156 |
| Confirmed by the release itself | 139 |
| Carried by a second registry | 13 |
| Confirmed by an independent source | 0 |
| Unverified | 4 |
| Release-note lines read | 2,933 - 17 breaking, 2 deprecations, 308 features, 948 fixes, 1,658 chores |
| Job posts searched | about 1,200, the last three "Ask HN: Who is hiring?" threads |
| Recommendations | 5 update a chapter, 2 new lesson, 30 watch |
| Chapters with something to act on | 11 of 25 |
| Course notebooks read | 89, across six weeks |
| Chapters installing something with no version bound | 19 of 25 |
| Removed APIs still called in the material | 7 |
| Tests | 285. None calls a model or the network |

---

## "Why would a school care about langchain 1.4.2?"

It should not, and that is the question that reshaped the agent.

The first version decided by version number. A package scored higher the more often it
shipped, market relevance was how much Hacker News talked about it, and the judge rating
teaching value was shown "langchain version 1.4.2 was released" and nothing else. It rated 29
of 37 packages 2 out of 5 and nothing above 3, because it could not tell a new concept from a
dependency bump.

A school asks three different questions, and the agent now answers each from data:

| The question | Where the answer comes from |
|---|---|
| Did something we teach break? | removed APIs found in the course notebooks, and breaking changes in the release notes |
| Is there a new concept worth a lesson? | the `feat:` and "Features" lines of the release notes, read by a judge told to think as a head of curriculum |
| Do employers want it? | job posts naming the tool in the last three "Who is hiring?" threads, and PyPI installs |

The release notes were already being collected and thrown away. Read now, they show why
versions mislead: of 2,933 lines, nine in ten are fixes or chores. About one line in nine is
something a teacher would read.

What changed as a result, in the same data:

- **crewai** had been "add a new lesson". Four job posts in three months. It is now watched,
  with the reason "few employers ask for it yet".
- **torch and torchvision** had been "update chapter C4" because the notebook pins 2.5.1 and
  2.14.0 exists. The
  notebook is pinned, so it runs for a student exactly as written, and nothing in what we read
  says the approach changed. It is now watched.
- **Six more PyPI-only packages** (dspy, evidently, faiss-cpu, openai, peft, streamlit) had
  been "update the chapter" with no release notes to read at all: the version was the only
  reason. They are watched, with advice to pin.
- **langchain** is still "update chapter C8", even though its recent releases scored 1 out of 5
  for teaching. That is correct: the notebooks call `RetrievalQA`, which 1.x removed, so the
  material does not run. A broken notebook is a teaching problem whatever the release notes say.

The result: 5 chapter updates and 2 new lessons, each with a reason a teacher would accept,
out of 37 packages that shipped something.

## "Why is cross-source zero? Is the checker broken?"

Still zero, with a second tier-1 source added. The model reads every discussion post that names
a package we track and reports what each one actually claims. **None of them stated anything a release page could check.** People
discuss tools; they do not report version numbers. The count for a given run is printed in the
log as `model read N discussion posts, 0 stated something a release page can check`.

A claim with no version has nothing to check against, so it stays unverified. Zero is the
honest answer for this week's data, and the page says zero rather than rounding it into the
primary-report column.

Watch for this trap in the question: cross-source is the *hardest* verdict we can award, so a
high number would be the suspicious one.

## "So what does 'confirmed' actually mean?"

A tier-1 source - an official release or the PyPI registry - states the same subject at the
exact same version. Three rules make it strict:

1. **Tier 1 only.** A Hacker News post never confirms anything.
2. **Exact version equality.** We extract the version and compare with `==`. An early bug had
   `1.5` "confirmed" by `v11.5.0` because it used a substring test.
3. **Never self-confirmation.** A claim cannot be confirmed by the document it was read from.
   Every claim carries `source_signal_id`, and the verdict records what kind of check it was.

There are three kinds, and they are not worth the same:

| Verdict | What happened | Confidence |
|---|---|---|
| `primary_report` | The release states its own version and we cite that release | 0.70 |
| `registry_match` | GitHub and PyPI both carry the version, two records from the same publisher | 0.80 |
| `cross_source` | Something said elsewhere was confirmed by an official release | 0.90 |

Adding PyPI could have made cross-source look non-zero overnight. It does not, because two
registries run by the same project are not independent of each other, and calling that a
cross-source check would have been us grading our own homework. It gets its own name.

## "You use an LLM. How do we know it isn't making this up?"

The model never decides anything that appears as evidence. It does three jobs:

- reads a discussion post and reports what it claims
- rates how much a change matters for teaching, recorded as `judged`, never `measured`
- writes the recommendation sentence

**The verification gate is rules.** No model output can turn a claim into `confirmed`.

The writer is also checked. If the sentence it returns drops the facts it was given - the
version number, or the name of the removed API - the sentence is refused and the rules text
is used instead. The run log prints it when that happens:

    think: the written sentence for langchain dropped the facts, keeping ours

## "Why one agent and not one per stage?"

Because the stages have nothing to negotiate. Each one reads the previous artifact and writes
the next: collect, cluster, verify, score, decide. Five agents would need a protocol between
them and would buy no decision that a function call does not already make. We spent the
complexity where it changes the answer instead: on the verification gate and on reading the
curriculum.

## "How do you know a chapter is out of date? Isn't that a guess?"

It was, until we read the notebooks. `python -m src.curriculum` reads all 89 and records three
things per chapter: the version bound each `pip install` line carries, the packages installed
with no bound at all, and the API calls a later major release removed.

Then the verdict is arithmetic:

| What we find | Verdict |
|---|---|
| The notebook calls an API a newer release removed | rewrite - the material does not run |
| A major release since the pinned version | rewrite - semver says a major breaks things |
| A minor gap, with a breaking change or new concept in the notes | rewrite |
| A minor gap, with only fixes and chores in the notes | watch - the pinned notebook still runs |
| No bound, and the releases add something worth teaching | rewrite |
| No bound, and nothing read shows a change worth teaching | watch, and pin it |
| No chapter, and employers ask for it | a new lesson |
| No chapter, and few employers ask | watch |

That last distinction matters. Without it the run produced 24 chapter updates, including
"update chapter C24" because pandas moved. Pandas moving is a dependency-hygiene problem;
`RetrievalQA` disappearing is a curriculum problem. Twelve survive the distinction.

Patch-only movement can no longer ask for a rewrite. That rule alone removed a recommendation
that read "update chapter C19 due to three confirmed claims" - three patch releases of the
same minor line.

## "Give us one finding that actually matters."

Chapter C8, document QA on LangChain, eight notebooks.

- Seven install `langchain` with **no version bound**.
- One pins `langchain==0.0.352` and `openai==0.28`.
- The code calls `RetrievalQA`, `LLMChain`, `load_qa_chain` and `openai.ChatCompletion`.

All four are gone in 1.x. The newest confirmed release this run is **langchain 1.4.2**. A
student who runs that notebook today installs 1.4.2, and the material does not run.

The rest of the course pins `langchain==0.3.*`, `langchain-openai==0.2.*`, `langgraph==0.2.*`
- one major version behind every confirmed release in this run.

## "The removed-API list - is that verified too?"

No, and the page says so. Those come from a pattern table we wrote, so they are labelled as
coming from our table, never mixed with confirmed evidence. It is a flag for a human to check,
not a verdict.

## "What happens if the wifi dies during the demo?"

Two fallbacks. Both were run with the network and the model switched off, on 2026-09-19:

1. **Re-analyse** in the web app replays the saved signals of any past run. Replaying the
   frozen run with no model and no network produced the same 17 recommendations and the same
   4 chapter updates, with the reasons intact. Without a model the sentences come from the
   rules instead of being rewritten, and the page says which.
2. `web/dist/site.html` is a single file with the run and the fonts embedded. It opens on any
   machine with no server and no network.

## "What would you do with another two weeks?"

- Widen the collection window so cross-source has a chance to be non-zero.
- Replace the pattern table with a real check: read the release notes for removal notices
  instead of matching names we typed ourselves.
- Difficulty is still a constant 2 in the score. Either measure it or drop the dimension.
