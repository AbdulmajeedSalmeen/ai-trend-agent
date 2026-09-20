import contextlib
import io
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src import runio, trace
from src.adapters import model
from src.pipeline import STAGES

LOCK_PATH = runio.RUNS_DIR / ".run.lock"
MIN_GITHUB_BUDGET = 12

_state_lock = threading.Lock()
_status = {
    "state": "idle",
    "run_id": None,
    "mode": None,
    "stage": None,
    "stage_index": 0,
    "stage_count": len(STAGES),
    "log": [],
    "started_at": None,
    "finished_at": None,
    "error": None,
    "thoughts": [],
    "model": None,
}


def status() -> dict:
    with _state_lock:
        return {**_status, "log": list(_status["log"]), "thoughts": list(_status["thoughts"])}


def _set(**fields) -> None:
    with _state_lock:
        _status.update(fields)


def _log(line: str) -> None:
    line = line.rstrip()
    if not line:
        return
    with _state_lock:
        if line.startswith("think:"):
            _status["thoughts"].append(line[6:].strip())
            del _status["thoughts"][:-40]
        else:
            _status["log"].append(line)
            del _status["log"][:-200]


class _LogStream(io.TextIOBase):
    def __init__(self, mirror):
        self.mirror = mirror
        self.buffer_text = ""

    def write(self, text: str) -> int:
        self.mirror.write(text)
        self.buffer_text += text
        while "\n" in self.buffer_text:
            line, self.buffer_text = self.buffer_text.split("\n", 1)
            _log(line)
        return len(text)


def github_budget(token: str | None = None) -> int:
    token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()["resources"]["core"]["remaining"]


def _acquire_lock(run_id: str) -> bool:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{run_id} {datetime.now(timezone.utc).isoformat()}")
    return True


def _release_lock() -> None:
    LOCK_PATH.unlink(missing_ok=True)


def _execute(run_id: str, replay: bool) -> None:
    stages = [s for s in STAGES if not (replay and s[0] == "ingest")]
    run_path = runio.run_dir(run_id)
    mirror = io.StringIO()
    started = time.time()

    # A run from the browser is a run: it gets its own trace, and a model that
    # was halted by a spent quota an hour ago gets another chance now.
    model.reset()
    record = trace.start(run_id, model.describe())

    try:
        for index, (name, stage_run) in enumerate(stages, start=1):
            _set(stage=name, stage_index=index, stage_count=len(stages))
            trace.set_stage(name)
            _log(f"stage: {name}")
            with contextlib.redirect_stdout(_LogStream(mirror)):
                stage_run(run_path)
        record.halted = model.halted()
        record.save(run_path)
        totals = record.summary()
        _log(f"{totals['calls']} model calls, {totals['tokens']} tokens, ${totals['cost_usd']:.4f}")
        _log(f"done in {time.time() - started:.1f}s")
        _set(state="done", stage=None, finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        record.halted = model.halted()
        with contextlib.suppress(OSError):
            record.save(run_path)
        _log(f"failed during {_status['stage']}: {error}")
        _set(state="failed", error=str(error), finished_at=datetime.now(timezone.utc).isoformat())
    finally:
        _release_lock()


def start(replay_run_id: str | None = None) -> dict:
    if status()["state"] == "running":
        return {"ok": False, "reason": "already_running", "status": status()}

    if replay_run_id is None:
        try:
            remaining = github_budget()
        except Exception as error:
            return {"ok": False, "reason": f"github_unreachable: {error}"}
        if remaining < MIN_GITHUB_BUDGET:
            return {"ok": False, "reason": "github_budget", "remaining": remaining}

    run_id = replay_run_id or runio.new_run_id()

    if replay_run_id and not (runio.RUNS_DIR / replay_run_id / "signals.json").exists():
        return {"ok": False, "reason": "no_saved_signals"}

    if not _acquire_lock(run_id):
        return {"ok": False, "reason": "locked"}

    _set(
        state="running",
        run_id=run_id,
        mode="replay" if replay_run_id else "live",
        stage=None,
        stage_index=0,
        log=[],
        thoughts=[],
        model=model.describe(),
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
        error=None,
    )
    _log(f"{'replaying' if replay_run_id else 'live run'} {run_id}")

    thread = threading.Thread(target=_execute, args=(run_id, bool(replay_run_id)), daemon=True)
    thread.start()
    return {"ok": True, "run_id": run_id, "mode": "replay" if replay_run_id else "live"}


def list_runs() -> list[dict]:
    runs = []
    for path in sorted(runio.RUNS_DIR.glob("run_*"), reverse=True):
        artifacts = {name: (path / f"{name}.json").exists()
                     for name in ["signals", "trends", "scores", "recommendations"]}
        runs.append({
            "run_id": path.name,
            "complete": all(artifacts.values()),
            "artifacts": artifacts,
            "modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return runs
