# Demo answers

Every number here comes from `run_20260919T152501Z`. Re-run `python -m src.pipeline --run-id
run_20260919T152501Z` and they come back the same, because replay never touches the network.

## The run, in numbers

| | |
|---|---|
| Signals collected | 393 - 313 Hacker News, 80 GitHub releases |
| Subjects tracked | 17 |
| Checkable claims | 82 |
| Confirmed by the release itself | 80 |
| Confirmed by an independent source | 0 |
| Unverified | 2 |
| Recommendations | 4 update a chapter, 4 new lesson, 9 watch |
| Course notebooks read | 89, across six weeks |
| Chapters installing something with no version bound | 19 of 25 |
| Removed APIs still called in the material | 7 |
| Tests | 149, in 15 files. None calls a model or the network |

---

## "Why is cross-source zero? Is the checker broken?"

No. The model reads every discussion post that names a package we track and reports what each
one actually claims. **None of them stated anything a release page could check.** People
discuss tools; they do not report version numbers. The count for a given run is printed in the
log as `model read N discussion posts, 0 stated something a release page can check`.

A claim with no version has nothing to check against, so it stays unverified. Zero is the
honest answer for this week's data, and the page says zero rather than rounding it into the
primary-report column.

Watch for this trap in the question: cross-source is the *hardest* verdict we can award, so a
high number would be the suspicious one.

## "So what does 'confirmed' actually mean?"

A tier-1 source - an official release - states the same subject at the exact same version.
Three rules make it strict:

1. **Tier 1 only.** A Hacker News post never confirms anything.
2. **Exact version equality.** We extract the version and compare with `==`. An early bug had
   `1.5` "confirmed" by `v11.5.0` because it used a substring test.
3. **Never self-confirmation.** A claim cannot be confirmed by the document it was read from.
   Every claim carries `source_signal_id`, and evidence from a different document is labelled
   `cross_source` while the release speaking about itself is `primary_report`.

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
| Major or minor release since the pinned version | worth rewriting |
| Only patch releases since | leave it alone |
| No bound in the notebook at all | no guarantee - a student installs whatever shipped that day |
| Nothing recorded | say so, do not call the chapter stale |

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

Two fallbacks:

1. **Re-analyse** in the web app replays the saved signals of any past run. No network.
2. `web/dist/site.html` is a single file with the run and the fonts embedded. It opens on any
   machine with no server and no network.

## "What would you do with another two weeks?"

- Widen the collection window so cross-source has a chance to be non-zero, and track PyPI
  release feeds directly rather than GitHub releases alone.
- Replace the pattern table with a real check: read the release notes for removal notices
  instead of matching names we typed ourselves.
- Difficulty is still a constant 2 in the score. Either measure it or drop the dimension.
