import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# USD per million tokens, in and out. Unknown models cost nothing we can report.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
}

DEFAULT_BUDGET = 400_000


@dataclass
class Step:
    stage: str
    action: str
    ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    ok: bool = True
    note: str = ""


@dataclass
class Trace:
    """Every model call this run made, with what it cost and how long it took.

    A run is not reproducible and not answerable for its cost unless this exists.
    The budget is a hard ceiling: once it is spent the model is treated as absent
    and the stages fall back to rules, which they already know how to do.
    """

    run_id: str = ""
    model: str = ""
    budget: int = DEFAULT_BUDGET
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    steps: list[Step] = field(default_factory=list)
    stage: str = "-"
    halted: str | None = None

    def record(self, action: str, ms: float, tokens_in: int = 0, tokens_out: int = 0,
               ok: bool = True, note: str = "") -> Step:
        step = Step(self.stage, action, round(ms, 1), tokens_in, tokens_out, ok, note)
        self.steps.append(step)
        return step

    @property
    def tokens(self) -> int:
        return sum(step.tokens_in + step.tokens_out for step in self.steps)

    def over_budget(self) -> bool:
        return self.tokens >= self.budget

    def cost(self) -> float:
        rate_in, rate_out = PRICES.get(self.model.split(":")[-1], (0.0, 0.0))
        spent = sum(step.tokens_in * rate_in + step.tokens_out * rate_out for step in self.steps)
        return round(spent / 1_000_000, 6)

    def by_stage(self) -> dict:
        totals: dict[str, dict] = {}

        for step in self.steps:
            entry = totals.setdefault(step.stage, {"calls": 0, "ms": 0.0, "tokens": 0, "failed": 0})
            entry["calls"] += 1
            entry["ms"] += step.ms
            entry["tokens"] += step.tokens_in + step.tokens_out
            entry["failed"] += 0 if step.ok else 1

        for entry in totals.values():
            entry["ms"] = round(entry["ms"], 1)

        return totals

    def summary(self) -> dict:
        calls = len(self.steps)
        failed = sum(1 for step in self.steps if not step.ok)

        return {
            "run_id": self.run_id,
            "model": self.model,
            "started_at": self.started_at,
            "calls": calls,
            "failed_calls": failed,
            "tokens": self.tokens,
            "budget": self.budget,
            "budget_spent": round(self.tokens / self.budget, 4) if self.budget else 0.0,
            "cost_usd": self.cost(),
            "halted": self.halted,
            "ms": round(sum(step.ms for step in self.steps), 1),
            "slowest_ms": round(max((step.ms for step in self.steps), default=0.0), 1),
            "by_stage": self.by_stage(),
        }

    def save(self, run_dir: Path) -> None:
        payload = {"summary": self.summary(), "steps": [asdict(step) for step in self.steps]}
        (run_dir / "trace.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


current = Trace()


def start(run_id: str, model: str, budget: int = DEFAULT_BUDGET) -> Trace:
    global current
    current = Trace(run_id=run_id, model=model, budget=budget)
    return current


def set_stage(name: str) -> None:
    current.stage = name


def budget_left() -> bool:
    return not current.over_budget()
