# Demo answers

Every number here comes from `run_20260921T104824Z`. Re-run `python -m src.pipeline --run-id
run_20260921T104824Z` and they come back the same, because replay never touches the network.

## The run, in numbers

| | |
|---|---|
| Signals collected | 483 - 315 Hacker News, 88 PyPI releases, 80 GitHub releases |
| Packages followed | 53 when collected; the course notebooks now install 56 |
| Subjects tracked | 37 |
| Checkable claims | 156 |
| Confirmed by the release itself | 139 |
| Carried by a second registry | 13 |
| Confirmed by an independent source | 0 |
| Unverified | 4 |
| Release-note lines read | 2,933 - 17 breaking, 2 deprecations, 308 features, 948 fixes, 1,658 chores |
| Job posts searched | about 1,200, the last three "Ask HN: Who is hiring?" threads |
| Recommendations | 4 update a chapter, 1 course-wide change, 2 new lesson, 2 optional, 28 watch |
| Chapters with something to act on | 11 of 25 |
| Course notebooks read | 89, across six weeks |
| Chapters installing something with no version bound | 19 of 25 |
| Import lines to change | 85 in 39 notebooks across 11 chapters, checked against langchain 1.4.2; 3 break on today's install |
| Concepts the course does not teach | MCP, a new lesson: 20 job posts in three months, 0 of 89 notebooks |
| Tests | 352. None calls a model or the network |

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

- **crewai** had been "add a new lesson". Four job posts in three months. It is now optional
  content: an elective notebook outside the core path, until more employers ask for it.
- **torch and torchvision** had been "update chapter C4" because the notebook pins 2.5.1 and
  2.14.0 exists. The
  notebook is pinned, so it runs for a student exactly as written, and nothing in what we read
  says the approach changed. It is now watched.
- **Six more PyPI-only packages** (dspy, evidently, faiss-cpu, openai, peft, streamlit) had
  been "update the chapter" with no release notes to read at all: the version was the only
  reason. They are watched, with advice to pin.
- **langchain** is a course-wide decision, even though its recent releases scored 1 out of 5
  for teaching. Checked against the langchain 1.4.2 source, 85 import lines in 39 notebooks
  across 11 chapters name something the release no longer has. One notebook breaks on today's
  install; the other 38 pin LangChain 0.3 and teach its agent API. A broken or outdated
  notebook is a teaching problem whatever the release notes say.

The result: 4 chapter updates, 1 course-wide change, 2 new lessons and 2 optional notebooks,
each with a reason a teacher would accept and a two or three step plan, out of 37 packages
that shipped something.

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

## "Is the Arabic machine-translated?"

No, and no model writes it. Each card's Arabic reason is built from the same rules and the
same facts as the English one: the same versions, dates, counts, install figures and
priority, character for character. The model may rewrite the English sentence, but our checks
on a written sentence look for English phrases, so an Arabic sentence from a model could not
be held to the same standard. The release-note lines quoted in brackets stay in English,
because they are quotes.

A test builds both languages for every combination the rules can meet, 11,664 cards, plus the
37 cards of the frozen run, and fails if the Arabic carries a figure the English does not.
The only differences allowed are zero, one and two, which Arabic writes as words.

## "Why one agent and not one per stage?"

Because the stages have nothing to negotiate. Each one reads the previous artifact and writes
the next: collect, cluster, verify, score, decide. Five agents would need a protocol between
them and would buy no decision that a function call does not already make. We spent the
complexity where it changes the answer instead: on the verification gate and on reading the
curriculum.

## "How do you know a chapter is out of date? Isn't that a guess?"

It was, until we read the notebooks. `python -m src.curriculum` reads all 89 and records three
things per chapter: the version bound each `pip install` line carries, the packages installed
with no bound at all, and every `langchain` import, checked against the newest release.

Then the verdict is arithmetic:

| What we find | Verdict |
|---|---|
| A notebook imports a name the newest release removed, with no bound | rewrite - it does not run on today's install |
| The same import in a notebook that pins the old line | an edit for the day the course moves |
| A major release since the pinned version | rewrite - semver says a major breaks things |
| A minor gap, with a breaking change or new concept in the notes | rewrite |
| A minor gap, with only fixes and chores in the notes | watch - the pinned notebook still runs |
| No bound, and the releases add something worth teaching | rewrite |
| No bound, and nothing read shows a change worth teaching | watch, and pin it |
| Notebooks in two or more chapters import names the release removed | investigate a larger change |
| No chapter, and employers ask for it | a new lesson |
| No chapter, some employers ask, and there is something to teach | optional content |
| No chapter, and no employer asks | watch |

That last distinction matters. Without it the run produced 24 chapter updates, including
"update chapter C24" because pandas moved. Pandas moving is a dependency-hygiene problem;
`RetrievalQA` disappearing is a curriculum problem. Twelve survive the distinction.

Patch-only movement can no longer ask for a rewrite. That rule alone removed a recommendation
that read "update chapter C19 due to three confirmed claims" - three patch releases of the
same minor line.

## "Give us one finding that actually matters."

The course teaches LangChain 0.3's agent API, and LangChain 1.x removed it.

- 38 notebooks import `AgentExecutor` and `create_react_agent` from `langchain.agents`. In
  langchain 1.4.2 that module exports two names, `create_agent` and `AgentState`. The page links
  the file at the release tag, so anyone can open it and count.
- They still run, because they pin `langchain==0.3.*` or `<1.0`. Nothing breaks today; the
  students learn an API the current release no longer has.
- One notebook does break today. `Demo_LangChain_Document_Chat` in C8 installs `langchain` with
  no bound, and cell 88 still says `from langchain.chains import RetrievalQA`. The proposed line,
  `from langchain_classic.chains import RetrievalQA`, was read from langchain-classic 1.0.8.

So the recommendation is not "update C8". It is: fix that one notebook now, then decide once,
for the whole course, whether to stay on 0.3 or move to 1.x, with the 85 lines listed cell by
cell for the day it moves.

## "Does it tell a teacher what to change in the material?"

Yes. Each recommendation carries a plan of two or three steps, and a course-wide one carries
the edit list: notebook, cell, the current line, the proposed line, and why, in English and
Arabic. For langchain the plan reads:

1. First fix what breaks on today's install: 3 import lines in 1 notebook (C8).
2. Decide once, for the whole course: stay on the langchain line 38 notebooks pin (0.3.*,
   >=0.1.0,<1.0), or move to langchain 1.4.2.
3. To move, change 85 import lines in 39 notebooks across 11 chapters; the edit list names
   each cell.

Every step is built by rules from facts the run holds, so the Arabic plan has the same steps
and the same numbers. A plan never asks to pin a pre-release: dspy's newest confirmed version
is 3.4.0b1, so its plan says to pin the newest stable release instead.

## "Is there a new idea the course should teach, not just a new version?"

Yes, and it is found the same way the edits are: from the tools' own source, not from what
people say about them. For each tool the course teaches, the agent lists the modules at the
newest version the course's pins allow, and at the newest release, both read at their tags on
GitHub. What the newest release added is a candidate, described by its own docstring.

langchain went from 0.3.30 to 1.4.2 and gained `langchain.mcp`: "LangChain MCP adapters for
connecting MCP servers with LangChain applications". 20 job posts named MCP in the last three
"Who is hiring?" threads, and none of the 89 notebooks mentions it, in code or in prose. That
makes it a new lesson.

Five more modules are new, among them `langgraph.stream` and `langchain.rate_limiters`. They
are listed and watched, not counted: a name like "stream" would match every job post, so
demand is left unmeasured rather than invented. The release notes of this run never mention
MCP at all, and Hacker News titled it twice; reading the code found what reading the chatter
missed.

## "The removed-API list - is that verified too?"

For LangChain, yes, and checking it corrected us. The first version matched names from a
pattern table we typed, and flagged four removed APIs in C8: `RetrievalQA`, `LLMChain`,
`load_qa_chain` and `openai.ChatCompletion`. Checked against the release:

- `RetrievalQA` and `load_qa_chain` were imported from `langchain_classic` in five notebooks,
  where they still work. One line imported `RetrievalQA` from the old path, and that one is real.
- `LLMChain` only matched inside `LLMChainExtractor`, a different class.
- `openai.ChatCompletion` only appeared in a comment explaining the change to the new client.

So every `langchain` import is now checked against the source of the newest release, read at
its tag on GitHub, and the name it moved to is found the same way. The table still covers a
few calls outside LangChain, such as `openai.ChatCompletion`, and those are labelled as coming
from our table. It no longer reads comments, and a name must match whole.

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
- Extend the release check past LangChain, to the openai and langgraph calls the table still
  covers by name.
- Flag pins that fight each other. One lab pins `langchain==0.0.352` in one cell and installs
  the 1.x family in the next.
- Read more tools for new concepts than langchain and langgraph, and find a way to measure
  demand for concepts whose names are common words, such as streaming.
- Difficulty is still a constant 2 in the score. Either measure it or drop the dimension.
