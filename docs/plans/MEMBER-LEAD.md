# Lead (Abdulmajeed) — Schema, Stage 4, Pipeline, Repo

**Mission:** you own the contract everyone codes against, the glue that joins the stages,
the smallest stage (Stage 4), and the GitHub repo. You are the person who makes four
separate stages become one system.

**You will learn:** pydantic models, LangGraph, JSON file IO, CLI design, running a team on git.

**Files you own:**
- `src/schema.py` — the data models (written WITH the team on Sep 15)
- `src/runio.py` — run-folder helpers everyone imports
- `src/stages/stage4_act.py` + `tests/test_stage4.py`
- `src/pipeline.py` — LangGraph graph + CLI
- `docs/PROGRESS.md` — updated daily from standup

---

## Sep 15 — run the schema workshop (90 minutes, all four)

Agenda you drive:
1. 10 min — walk through TEAM-PLAN.md architecture. Everyone must be able to say
   what their stage reads and writes.
2. 50 min — write `src/schema.py` together, projector or screen share, one person types.
   Build each model by asking "what does the NEXT stage need from this?"
3. 20 min — write `tests/test_schema.py` together: one valid object per model,
   one invalid (naive datetime must be rejected).
4. 10 min — commit, push to dev, watch CI go green together.

Target schema (do NOT paste this — make the team derive it; steer them here):

```python
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, field_validator


class Signal(BaseModel):
    id: str
    source: Literal["hackernews", "github"]
    tier: Literal[1, 2]
    subject: Optional[str] = None
    title: str
    url: str
    published_at: datetime
    body: str = ""

    @field_validator("published_at")
    @classmethod
    def must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("published_at must be timezone-aware UTC")
        return v


class Claim(BaseModel):
    text: str
    subject: str
    version: Optional[str] = None
    verdict: Literal["confirmed", "unverified"] = "unverified"
    evidence_url: Optional[str] = None
    confidence: float = 0.2


class Trend(BaseModel):
    id: str
    subject: str
    signal_ids: list[str]
    claims: list[Claim]


class Score(BaseModel):
    trend_id: str
    chapter_id: Optional[str] = None
    confidence: float
    dimensions: dict[str, int]
    provenance: dict[str, str]
    priority: float


class Recommendation(BaseModel):
    trend_id: str
    action: Literal["update_existing_material", "add_new_lesson", "watch"]
    chapter_id: Optional[str] = None
    rationale: str
```

## Sep 16 — `src/runio.py`, the helpers all four stages import

```python
import json
from datetime import datetime, timezone
from pathlib import Path

RUNS_DIR = Path("fixtures/runs")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def run_dir(run_id: str) -> Path:
    d = RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "raw").mkdir(exist_ok=True)
    return d


def save_artifact(run_dir: Path, name: str, items: list) -> None:
    """items = list of pydantic models. name = 'signals', 'trends', ..."""
    path = run_dir / f"{name}.json"
    path.write_text(
        json.dumps([i.model_dump(mode="json") for i in items], indent=2),
        encoding="utf-8",
    )


def load_artifact(run_dir: Path, name: str, model) -> list:
    path = run_dir / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [model.model_validate(item) for item in data]
```

Write `tests/test_runio.py`: save a list with one Signal, load it back, assert equal.
Push same day — B, C, D all import this on Sep 17.

## Sep 17 — Stage 4: action mapping

`src/stages/stage4_act.py`. Reads `trends.json` + `scores.json`, writes `recommendations.json`.

The decision table (this IS the stage — code it exactly):

| Condition (checked top to bottom) | Action |
|---|---|
| confidence < 0.5 | `watch` — never act on unverified gossip |
| priority >= 3.0 and chapter_id is not null | `update_existing_material` |
| priority >= 2.5 and chapter_id is null | `add_new_lesson` (curriculum gap) |
| everything else | `watch` |

```python
def decide_action(score: Score) -> str:
    # TODO: implement the table above, top to bottom, first match wins
    ...


def build_rationale(trend: Trend, score: Score, action: str) -> str:
    # One honest sentence naming: the subject, the verdict of its best claim,
    # and the chapter title if matched. No hype words.
    ...


def run(run_dir: Path) -> None:
    # load trends + scores, pair them by trend_id, decide, save recommendations
    ...
```

Tests (write these BEFORE the code — they are the table):
- confidence 0.4, priority 4.0 → `watch` (floor beats priority)
- confidence 0.9, priority 3.2, chapter C6 → `update_existing_material`
- confidence 0.9, priority 2.7, no chapter → `add_new_lesson`
- confidence 0.9, priority 2.0, chapter C6 → `watch`

## Sep 18 — pipeline CLI with stub stages

`src/pipeline.py` — runnable TODAY even though teammates' stages are half-done,
because you call them through one interface:

```python
import argparse
from pathlib import Path

from src.stages import stage1_ingest, stage2a_cluster, stage2b_verify, stage3_score, stage4_act
from src import runio

STAGES = [
    ("ingest", stage1_ingest.run),
    ("cluster", stage2a_cluster.run),
    ("verify", stage2b_verify.run),
    ("score", stage3_score.run),
    ("act", stage4_act.run),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None, help="reuse an existing run folder")
    args = parser.parse_args()
    rid = args.run_id or runio.new_run_id()
    rd = runio.run_dir(rid)
    for name, fn in STAGES:
        print(f"[{rid}] stage: {name}")
        fn(rd)
    print(f"[{rid}] done")


if __name__ == "__main__":
    main()
```

If a teammate's file does not exist yet, create it with a stub `def run(run_dir): print("stub")`.
Command to verify: `python -m src.pipeline` — should print all five stage names.

## Sep 19 — LangGraph wrapper

Replace the plain loop with a LangGraph `StateGraph`. State = `{"run_dir": str}`.
Each node is a tiny function calling one stage's `run()`. Edges in stage order.

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict


class PipelineState(TypedDict):
    run_dir: str


def build_graph():
    g = StateGraph(PipelineState)
    # TODO: one node per stage; each node calls stage.run(Path(state["run_dir"]))
    #       and returns state unchanged
    # TODO: START -> ingest -> cluster -> verify -> score -> act -> END
    return g.compile()
```

Keep the plain loop as `run_sequential()` — one test asserts both produce identical files.
That test is your descope insurance: if LangGraph fights you, demo runs on the loop.

## Sep 20 — you chair Integration 1

Checklist:
- [ ] Everyone pulls dev, `pytest` green on all four laptops
- [ ] `python -m src.pipeline` on the shared fixture data, end to end
- [ ] Read every artifact out loud together — does trends.json actually match what Stage 3 expects?
- [ ] Every mismatch: decide the fix together, ONE person implements it, others watch
- [ ] Update docs/PROGRESS.md: what broke, what was learned

## Traps

1. You are the merge point — pull dev several times a day, not once.
2. Do not fix teammates' stages yourself. Comment, explain, let them fix. Slower today, faster by Sep 20.
3. `git push --force` never. If git suggests it, stop and ask Claude.
4. If schema must change after Sep 15: announce in chat, change it, run FULL test suite, help every affected member the same hour.

## Definition of done (Sep 19 evening)

- [ ] `runio.py` + tests merged
- [ ] Stage 4 + 4 tests merged
- [ ] `python -m src.pipeline` runs all five stages on stubs/fixtures
- [ ] LangGraph graph runs, sequential fallback tested identical
- [ ] PROGRESS.md current
