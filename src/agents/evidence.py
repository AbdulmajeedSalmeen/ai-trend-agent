"""What an agent is allowed to look at: this run's own artifacts, and the course.

Nothing here reaches the network. Stage 1 already collected the releases, the market
numbers and the signals into the run directory, and the notebooks sit on the machine.
Reading from those keeps three properties the project depends on: a frozen run replays
offline with no keys, the tests never call anything, and every citation an agent makes
can be checked later against the same bytes the agent saw.
"""

import json
import re
from pathlib import Path

from src.notebooks import NOTEBOOK_DIR

MAX_HITS = 8


def _releases(run_dir: Path) -> list[dict]:
    raw = run_dir / "raw"
    if not raw.is_dir():
        return []
    out = []
    for path in sorted(raw.glob("github_*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def release_notes_tool(run_dir: Path):
    """What this run's releases say about a package, by the repository that shipped them."""
    blobs = _releases(Path(run_dir))

    def release_notes(package: str = "") -> str:
        name = str(package or "").strip().lower().replace("_", "-")
        if not name:
            return ""
        lines = []
        for blob in blobs:
            repo = str(blob.get("repo", ""))
            if name not in repo.lower().replace("_", "-"):
                continue
            for release in (blob.get("releases") or [])[:4]:
                title = str(release.get("name") or release.get("tag_name") or "")
                body = re.sub(r"\s+", " ", str(release.get("body") or ""))
                lines.append(f"{repo} {title}: {body[:600]}")
        return " | ".join(lines[:4])

    return release_notes


def course_uses_tool(notebook_dir: Path | None = None):
    """The notebook cells of the course that use a name, with their cell numbers."""
    root = Path(notebook_dir or NOTEBOOK_DIR)

    def course_uses(symbol: str = "") -> str:
        needle = str(symbol or "").strip()
        if len(needle) < 3:
            return "give a name of three characters or more"
        hits = []
        for path in sorted(root.glob("*/*.ipynb")):
            try:
                cells = json.loads(path.read_text(encoding="utf-8", errors="replace")).get("cells", [])
            except (OSError, json.JSONDecodeError):
                continue
            for position, cell in enumerate(cells, start=1):
                source = cell.get("source", "")
                source = "".join(source) if isinstance(source, list) else str(source)
                if needle in source:
                    hits.append(f"{path.name} cell {position}")
                    break
            if len(hits) >= MAX_HITS:
                break
        return f"{needle} appears in {len(hits)} notebooks: " + "; ".join(hits) if hits else f"no notebook uses {needle}"

    return course_uses


def demand_tool(market: list[dict] | None):
    """The job posts and installs this run already counted for a package."""
    rows = {str(row.get("subject")): row for row in (market or [])}

    def demand(subject: str = "") -> str:
        row = rows.get(str(subject or "").strip())
        if not row:
            return f"nothing counted for {subject}"
        jobs = row.get("jobs")
        downloads = row.get("downloads")
        months = row.get("months") or 3
        parts = []
        parts.append(f"{jobs} job posts in {months} months" if jobs is not None else "job posts not counted")
        if downloads is not None:
            parts.append(f"{downloads} installs")
        return f"{subject}: " + ", ".join(parts)

    return demand


def tools_for(run_dir: Path, market: list[dict] | None, notebook_dir: Path | None = None) -> dict:
    """The three tools, bound to one run. An agent gets these and nothing else."""
    return {
        "release_notes": release_notes_tool(run_dir),
        "course_uses": course_uses_tool(notebook_dir),
        "demand": demand_tool(market),
    }
