# Member D (Naif) — Stage 2b: Verification + Stage 3: Scoring

**Mission:** you build the project's soul. Every competing team will show an agent that
collects news. Ours is the one that CHECKS: a claim becomes `confirmed` only when an
official source this run actually fetched says exactly that. You also score each trend so
the curriculum team knows what matters most. Your two stages are small in lines and big
in thinking — the demo lives or dies on your verdict gate.

**You will learn:** designing decision rules, evidence-based logic, weighted scoring,
test-first development (your tests ARE the rules).

**Files you own:**
- `src/stages/stage2b_verify.py` + `tests/test_stage2b.py`
- `src/stages/stage3_score.py` + `tests/test_stage3.py`

**Your contract:** 2b reads `signals.json` + `trends.json`, rewrites `trends.json` with
verdicts filled. Stage 3 reads `trends.json` + `fixtures/curriculum.json`, writes `scores.json`.

---

## Sep 16 — the rules on paper, then as failing tests

Write the verdict rules in your notebook first. These are the law:

1. A claim can be **confirmed** only by a **tier-1 signal** (official release), never by
   a forum post. Forums repeat rumors; that is exactly what we refuse to trust.
2. The tier-1 signal must have the **same subject** as the claim.
3. The versions must be **exactly equal** (`==`). `"5.6"` vs `"5.6.1"` = different.
4. A claim with **no version cannot be confirmed** at all — nothing checkable in it.
5. Everything that fails any rule stays **unverified**. Unverified is not shameful —
   it is the honest answer, and half our demo.
6. Confirmed → `confidence = 0.9`, `evidence_url` = the tier-1 signal's url.
   Unverified → `confidence = 0.2`, `evidence_url = None`.

Now turn each rule into a pytest BEFORE writing the implementation. Build tiny helper:

```python
from datetime import datetime, timezone

from src.schema import Claim, Signal


def make_signal(subject, tier, title, url="https://example.com/x"):
    return Signal(
        id=f"s_{subject}_{tier}", source="github" if tier == 1 else "hackernews",
        tier=tier, subject=subject, title=title, url=url,
        published_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
```

The six tests (names say the rule):

```python
def test_exact_version_from_tier1_confirms(): ...
def test_forum_post_never_confirms(): ...          # tier 2 evidence -> unverified
def test_version_mismatch_stays_unverified(): ...  # claim 5.6 vs release 5.6.1
def test_versionless_claim_never_confirmed(): ...
def test_wrong_subject_never_confirms(): ...       # transformers release can't confirm langgraph claim
def test_confirmed_carries_evidence_url(): ...
```

Run `python -m pytest tests/test_stage2b.py` — all fail (nothing implemented). That
is correct test-first: tomorrow you make them pass one by one.

## Sep 17 — implement the verdict gate

```python
from pathlib import Path

from src import runio
from src.schema import Claim, Signal, Trend


def find_evidence(claim: Claim, signals: list[Signal]) -> Signal | None:
    """The one function the whole project is about. Return the tier-1 signal that
    proves the claim, or None. Apply rules 1-4 from your notebook, in order."""
    ...


def verify_claim(claim: Claim, signals: list[Signal]) -> Claim:
    """Returns a NEW claim with verdict/evidence_url/confidence set."""
    ...


def run(run_dir: Path) -> None:
    signals = runio.load_artifact(run_dir, "signals", Signal)
    trends = runio.load_artifact(run_dir, "trends", Trend)
    # verify every claim of every trend, save trends back
    ...
```

Make the six tests pass. Then add the nastiest one — the bug that fooled the original
version of this project for days:

```python
def test_same_version_different_subject_never_confirms():
    # langchain-core 1.5.4 must NOT confirm a claim about langchain-anthropic 1.5.4.
    # Same version number, different package. Subject match is rule 2 for a reason.
    ...
```

## Sep 18 — Stage 3: chapter matching + scoring

Chapter matching — simple word overlap, no ML:

```python
import json
from pathlib import Path


def load_chapters() -> list[dict]:
    return json.loads(Path("fixtures/curriculum.json").read_text(encoding="utf-8"))["chapters"]


def match_chapter(trend: Trend, chapters: list[dict]) -> str | None:
    """Lowercase word set of trend subject + claim texts vs word set of the chapter's
    topics_covered. 2+ shared words -> match, best chapter wins. Below 2 -> None.
    None is a GOOD answer: it means curriculum gap, which is what add_new_lesson needs."""
    ...
```

The five dimensions, v1 rules — deliberately simple, each 1–5:

| Dimension | v1 rule | provenance |
|---|---|---|
| relevance | 5 if trend subject appears in any chapter's topics, else 2 | measured |
| impact | 2 + min(3, number of signals in trend) | measured |
| educational_value | always 3 (no model yet — an honest constant) | default |
| difficulty | 2 (we cannot measure it yet) | default |
| market_relevance | 2 + min(3, number of TIER-2 signals) — forum buzz = market interest | measured |

`provenance` marks which numbers are real and which are placeholders — a defaulted 3
and a measured 3 must never look the same. This honesty is a demo talking point.

```python
WEIGHTS = {
    "relevance": 0.25, "impact": 0.25, "educational_value": 0.20,
    "difficulty": 0.10, "market_relevance": 0.20,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9  # module-level: broken weights = instant crash


def score_trend(trend: Trend, chapters: list[dict]) -> Score:
    # dimensions per table, priority = sum(dim * weight),
    # confidence = mean of the trend's claim confidences, chapter via match_chapter
    ...
```

Tests:
- weights sum to 1.0 (import the module, assert)
- a trend about "LangGraph" matches the agent-orchestration chapter (find its real
  chapter_id in fixtures/curriculum.json first — open the file and READ it)
- a trend about something absent from curriculum → chapter None
- priority of all-5s = 5.0, all-1s = 1.0
- confidence: one confirmed (0.9) + one unverified (0.2) claim → 0.55

## Sep 19 — wire both `run()` functions + PR

Full offline chain on C's fixture (once C pushed stage 2a — else use a hand-made
trends.json):

```bash
python -c "from pathlib import Path; import shutil; from src import runio; from src.stages import stage2a_cluster, stage2b_verify, stage3_score; rd = runio.run_dir('run_test_d'); shutil.copy('fixtures/samples/signals_fixture.json', rd / 'signals.json'); stage2a_cluster.run(rd); stage2b_verify.run(rd); stage3_score.run(rd); print((rd / 'scores.json').read_text(encoding='utf-8')[:600])"
```

Check by eye: at least one claim confirmed with evidence_url, at least one unverified.
That contrast IS the demo. `pytest` green, push, tell Lead.

## Traps

1. **Substring version check.** Only `==` on the full extracted version. Never `in`.
2. **Silence is not proof of anything.** A release that says nothing about a claim
   neither confirms nor refutes it. v1 has no `refuted` verdict on purpose — deciding
   something is FALSE needs stronger rules than we have time to build honestly.
3. **Both directions must exist in output.** If every claim comes back confirmed, your
   gate is broken-open (too loose). If every claim is unverified, it is broken-shut
   (too strict). The fixture must produce BOTH or something is wrong.
4. **Read curriculum.json before coding against it.** Chapters, `chapter_id`,
   `topics_covered` — the real field names, not the ones you imagine.

## Definition of done

- [ ] 7+ verdict tests green, written before the implementation
- [ ] 5+ scoring tests green
- [ ] Offline chain produces scores.json with a confirmed AND an unverified claim upstream
- [ ] Weights assert at import time
- [ ] provenance marks measured vs default on every dimension
