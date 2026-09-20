import json
from pathlib import Path

from src import runio

LOOKBACK = 8


def earlier_runs(run_id: str, runs_dir: Path | None = None, limit: int = LOOKBACK) -> list[Path]:
    """Runs collected before this one, newest first.

    Read from the run folders themselves rather than a memory file that a replay
    would mutate. Replaying a run therefore sees exactly the history it saw the
    first time, and a teammate with no saved runs simply has no history.
    """
    root = runs_dir or runio.RUNS_DIR

    if not root.exists():
        return []

    older = [path for path in sorted(root.glob("run_*")) if path.name < run_id]

    return list(reversed(older))[:limit]


def recommendations_of(run_path: Path) -> dict[str, dict]:
    """Subject to recommendation for one saved run, or nothing if it never finished."""
    path = run_path / "recommendations.json"
    trends_path = run_path / "trends.json"

    if not path.exists() or not trends_path.exists():
        return {}

    subjects = {t["id"]: t["subject"] for t in json.loads(trends_path.read_text(encoding="utf-8"))}
    found = {}

    for rec in json.loads(path.read_text(encoding="utf-8")):
        subject = subjects.get(rec["trend_id"])

        if subject:
            found[subject] = rec

    return found


def history(run_id: str, runs_dir: Path | None = None, limit: int = LOOKBACK) -> dict[str, dict]:
    """For each subject, how many runs in a row already asked for something to be
    done about it, and what the newest version was when we last looked.

    A run that only watched a subject breaks the streak: watching is not asking.
    """
    runs = earlier_runs(run_id, runs_dir, limit)
    by_run = [recommendations_of(path) for path in runs]
    subjects = {subject for found in by_run for subject in found}
    past = {}

    for subject in subjects:
        streak = 0
        first_run = None

        for run_path, found in zip(runs, by_run):
            rec = found.get(subject)

            if rec is None or rec["action"] == "watch":
                break

            streak += 1
            first_run = run_path.name

        seen_last = next((found[subject] for found in by_run if subject in found), None)

        past[subject] = {
            "runs": streak,
            "first_run": first_run,
            "last_version": (seen_last or {}).get("latest_version"),
        }

    return past


def recall(subject: str, action: str, latest_version: str | None, past: dict) -> dict:
    """What this run should say about a subject it has reported on before."""
    entry = past.get(subject)
    moved = bool(entry and latest_version and entry["last_version"]
                 and latest_version != entry["last_version"])

    if action == "watch" or entry is None or entry["runs"] == 0:
        return {"runs_flagged": 1, "first_seen_run": None, "version_moved": moved}

    return {
        "runs_flagged": entry["runs"] + 1,
        "first_seen_run": entry["first_run"],
        "version_moved": moved,
    }


def run_started(run_id: str):
    """The collection time encoded in a run id, or None if it is not one of ours."""
    from datetime import datetime, timezone

    try:
        stamp = datetime.strptime(run_id, "run_%Y%m%dT%H%M%SZ")
    except ValueError:
        return None

    return stamp.replace(tzinfo=timezone.utc)


def previous_run(run_id: str, runs_dir: Path | None = None) -> str | None:
    runs = earlier_runs(run_id, runs_dir, limit=1)

    return runs[0].name if runs else None
