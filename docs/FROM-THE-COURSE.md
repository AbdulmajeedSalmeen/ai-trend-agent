# What we took from the bootcamp, and what we left

We read all 89 notebooks and 27 slide decks, weeks 1 to 6. This records what came back
into the project, where each idea came from, and which ideas we deliberately did not take.
Leaving something out is a decision too, and the reason matters more than the count.

## Taken

### An execution trace with cost and latency
**From:** week 6, `Demo_Agent_Execution_Logging`, and the *Agent Observability and Monitoring*
deck: "if you cannot see how an agent thinks, you cannot reliably debug or improve it", plus
its per-trace budget section.

**What we built:** `src/trace.py`. Every model call is recorded with its stage, purpose,
latency, tokens in and out, and whether it succeeded. The run writes `trace.json` beside its
artifacts, and the page reports what the run cost and where the time went.

**What it caught immediately:** the very first traced run reported 170 model calls, 170
failures and zero tokens. Without the trace this looked like a slow but working run, because
every stage fell back to rules and still produced output. The key had hit its spend limit.

### A budget, and a circuit breaker
**From:** the same deck's "hard token ceilings, timeouts, maximum tool calls", and week 4 and
6's guardrails demos: allowlist over blocklist, hard limits, a fallback that explains itself.

**What we built:** a token ceiling for the whole run (`--budget`), and a rule that a refused
key, a revoked key or a spent quota stops the model for the rest of the run instead of being
retried. The stages already know how to work without a model.

**What it was worth:** the quota failure above cost one run 170 failed calls and about three
and a half minutes. The same replay now finishes in three seconds and says why.

### Memory between runs
**From:** week 5, `Demo_Long_Term_Memory_with_Vector_Store` and `Demo_Conversation_Memory`:
"in real-world use agents are rarely stateless".

**What we built:** `src/memory.py`. Each run reads the runs before it and reports whether a
recommendation is new or has been asked for several runs running, and whether the version has
moved since we last looked. A chapter flagged four runs in a row and still not acted on is a
different message from one flagged today.

**Where we differ from the course:** they reach for a vector store because their agents hold
free-text conversations. Our history is keyed by package name and version, so a keyed read of
the saved runs is exact where a similarity search would only be close. We also refused a
mutable memory file: history is derived from the run folders, so replaying a run sees exactly
the history it saw the first time.

### Refusing a sentence that contradicts the verdict
**From:** the *Agent Observability* deck, "the semantic success trap": valid JSON, correct
format, no errors, and still the wrong answer. And week 6's evaluator, whose
`has_no_unnegated_claims` exists because "the request was **not** sent successfully" must pass
while "the request was sent successfully" must not.

**What we built:** the sentence the model writes for a recommendation is refused if it drops
the facts it was given, and now also if it asserts something that undoes the verdict, such as
"up to date" on a chapter the rules just called behind. A phrase that is itself negated does
not count. When a sentence is refused the rules text is used and the log says so.

### PyPI as a second tier-1 source
**From:** week 2 and 3's habit of pinning nothing: `!pip install -U langchain`. The whole
course installs from PyPI, so PyPI is what a student actually receives.

**What we built:** `src/sources/pypi.py`, with the watchlist derived from the 53 packages the
notebooks install rather than typed by us. Two registries carrying the same version became its
own verdict, `registry_match`, rather than being passed off as an independent check.

### A baseline before the clever method
**From:** week 2, `BERT_for_Sentiment_Analysis`: TF-IDF and Naive Bayes are measured first, and
BERT is reported as ten points better than that baseline rather than as a good number on its own.

**What we did:** `docs/TUNING.md` already compares TF-IDF against sentence embeddings for
clustering, and records that TF-IDF won on this data. The course confirmed the habit rather
than starting it.

## Named, not newly built

These are things we had already done for our own reasons. The course gave them names worth
using out loud.

- **Grounded citations.** Week 6's evaluator checks `citations ⊆ evidence observed`. That is
  our `source_signal_id` rule: a claim can never be confirmed by the document it came from.
- **pass^k, not pass@k.** Week 6's *Agent Evaluation* deck: pass@k asks whether any run
  succeeded, pass^k whether every run did. Our stability question is pass^k.
- **Outcome versus process evaluation.** A correct final answer does not prove a correct
  execution. Our per-claim verdicts are process; the recommendation is outcome.
- **PASS / FAIL / INCONCLUSIVE.** The observability deck's point that stochastic systems need
  a third verdict. Our `unverified` is exactly that third verdict, and we report it rather
  than rounding it away.

## Left out, on purpose

- **Tool registries, dispatchers and tool-schema design** (weeks 3 and 4). These exist so an
  agent can choose between tools at runtime. Our five stages have no choice to make: each
  reads the previous artifact and writes the next. Adding a registry would be the shape of a
  solution without the problem.
- **`required_tool_sequence`, `no_forbidden_tool`, `correct_approval_boundary`, `max_calls`**
  from the week 6 evaluator. Same reason: no tool selection, no approval boundary.
- **Multi-agent supervisor and worker roles** (weeks 4 and 5). We considered five agents, one
  per stage, and rejected it: the stages have nothing to negotiate. This is the decision we
  expect to be asked about, and it was made on purpose rather than by default.
- **LLM-as-a-jury** (week 2, Evidently). Several judges voting, with disagreement surfaced. It
  is the right answer for a subjective rating and we cannot afford the calls this week. The
  cheap half of it, running the judge twice and treating disagreement as low confidence, is
  the first thing to add next.
- **DSPy and GEPA prompt optimisation** (week 2). Real, and too large for the time left.
- **FAISS index types, PEFT, LoRA, fine-tuning** (weeks 2 and 3). Nothing in this project
  trains or retrieves at a scale where they apply.

## Still owed

- The evaluation suite itself: a frozen set of cases from the saved run, several repeats per
  case, pass^k for stability, a release gate, and the result committed. The vocabulary above
  is in place; the measurement is not.
- Validating the judge against a reference, per the *Agent Evaluation* deck: "never assume the
  judge is ground truth".
