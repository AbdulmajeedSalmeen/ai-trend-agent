"""What a notebook teaches, and whether the field has moved past it.

This is the half of the product the packages cannot reach. An import that still
resolves and a version that is current say nothing about whether a lesson still
teaches the right method, and that question cannot be answered by a rule: somebody has
to read the notebook and then go and look at what the field does now.

So the reviewer is a loop. It reads the notebook in windows and decides what to look
up next: the releases this run collected, the research on a term. It answers with what
the notebook teaches, quoting the notebook, and what has happened to each technique,
citing what it read.

Two rules stand under it, and they are what make the output usable:

  1. Every quote it gives for what the material teaches is searched for in the
     notebook's own cells. Found, it carries that cell number. Not found, it is
     dropped. A reviewer cannot tell the course what it teaches on its own word.
  2. A status must be one the page knows, and a finding must name a technique the
     reviewer also said the notebook teaches. Anything else is dropped.

The output is one entry of material_review/1, the same file src/review.py already
reads, so nothing downstream has to learn a new shape. The review describes the course
in detail and the repository is public, so that file stays out of git.
"""

import json
import re
from pathlib import Path

from src import trace
from src.adapters import model

MAX_STEPS = 8
MAX_TOOL_CHARS = 3000
WINDOW = 12
STATUSES = ("superseded", "deprecated", "removed", "unsafe", "missing_context", "current")

SYSTEM = (
    "You are a curriculum reviewer for a bootcamp that trains people to build AI agents. "
    "You read one notebook and decide what it teaches and whether the field has moved past it. "
    "Read before you judge, and look things up before you claim they changed. "
    "Answer with one JSON object and nothing else, either "
    '{"tool": <name>, "args": {...}} to look, or, when you are ready, '
    '{"answer": {"teaches": [{"technique": <short name>, "as_taught": <one sentence>, '
    '"quote": <text copied exactly from a cell>}], '
    '"findings": [{"technique": <one of the names above>, "status": <' + "|".join(STATUSES) + ">, "
    '"now": <what the notebook does>, "instead": <what to teach in its place>, '
    '"why1": <one sentence>, "confidence": <high|medium|low>, '
    '"sources": [{"url": <where you read it>, "date": <YYYY-MM-DD or unknown>}]}]}}. '
    "Read the whole notebook before you answer: read_cells hands you a window, call it again "
    "for the next one. Name every technique the lesson teaches that somebody could be taught "
    "differently today, four to eight in a normal notebook, not only the first one you see. "
    "Check a technique before you judge it: release_notes for a package, papers for a method "
    "name. A judgement with nothing behind it is worth nothing. "
    "Quote the notebook exactly: a quote that is not in the notebook is dropped and your "
    "finding goes with it. Name a technique the notebook actually teaches, not one you expect. "
    "A lesson that is still the right way to teach something is worth saying so: status current, "
    "with no replacement."
)

TOOL_HELP = (
    "read_cells(start): the notebook's cells from this number, with their numbers.\n"
    "release_notes(package): what this run's releases say about a package.\n"
    "papers(term): how many papers named a term recently, and the newest of them."
)


def flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def whole(value, fallback: int = 1) -> int:
    """A number the model sent, which is a number only when it is one."""
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return fallback


def cells_of(path: Path) -> list[dict]:
    """Every cell with its number, counting from 1, the way the import check counts."""
    notebook = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    out = []
    for position, cell in enumerate(notebook.get("cells", []), start=1):
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else str(source)
        out.append({"cell": position, "kind": cell.get("cell_type", ""), "source": source})
    return out


def locate(quote: str, cells: list[dict]) -> int | None:
    """The cell a quote sits in, whole first, then its longest run of words.

    A reviewer rephrases as it reads, so an exact match alone drops findings that are
    honest. A window of its own words, found in one cell, is still the notebook's text
    and not the reviewer's memory.
    """
    needle = flat(quote)
    if len(needle) < 8:
        return None
    for cell in cells:
        if needle in flat(cell["source"]):
            return cell["cell"]
    words = needle.split()
    for width in (10, 7, 5):
        if len(words) < width:
            continue
        for start in range(0, len(words) - width + 1):
            window = " ".join(words[start:start + width])
            for cell in cells:
                if window in flat(cell["source"]):
                    return cell["cell"]
    return None


def read_cells_tool(cells: list[dict], window: int = WINDOW):
    """The notebook itself, handed over a window at a time so the agent chooses."""
    def read_cells(start: int = 1) -> str:
        first = whole(start)
        chosen = [c for c in cells if first <= c["cell"] < first + window]
        if not chosen:
            return f"no cells from {first}; this notebook has {len(cells)}"
        parts = [f"cell {c['cell']} ({c['kind']}): {c['source'][:700]}" for c in chosen]
        return f"cells {chosen[0]['cell']} to {chosen[-1]['cell']} of {len(cells)}. " + " || ".join(parts)
    return read_cells


def papers_tool(search=None):
    """Research activity around a name, from arXiv, or nothing when it cannot be asked."""
    def papers(term: str = "") -> str:
        if search is None:
            return "research was not checked on this run"
        try:
            found = search(str(term or ""))
        except Exception:  # a source that is down must not end the review
            return "research could not be checked"
        if not found:
            return f"no papers named {term}"
        newest = (found.get("recent") or [{}])[0]
        return (f"{found.get('papers')} papers named {term} in {found.get('days')} days; "
                f"newest: {newest.get('title', '')} {newest.get('published', '')}")
    return papers


def turn(notebook: str, cells: list[dict], seen: list[dict]) -> str:
    lines = [f"Notebook: {notebook}", f"It has {len(cells)} cells.", "", "Tools:", TOOL_HELP, ""]
    if seen:
        lines.append("What you have read so far:")
        for step in seen:
            lines.append(f"- {step['tool']}({json.dumps(step['args'], ensure_ascii=False)}): {step['text']}")
        # A window tool is easy to call once and forget, so say what is still unread.
        read = max((whole(s["args"].get("start")) for s in seen if s["tool"] == "read_cells"), default=0)
        if read and read + WINDOW <= len(cells):
            lines.append(f"You have not read past cell {read + WINDOW - 1} of {len(cells)}.")
    else:
        lines.append("You have read nothing yet. Start by reading cells.")
    lines += ["", f"You may call at most {MAX_STEPS} tools in total, then you must answer."]
    return "\n".join(lines)


def run(notebook: str, cells: list[dict], tools: dict, ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=1600, timeout=90,
                                                      action="reviewer_agent"))
    seen: list[dict] = []

    for _ in range(max_steps + 1):
        answer = ask(SYSTEM, turn(notebook, cells, seen))
        if not answer:
            return None

        proposal = answer.get("answer")
        if isinstance(proposal, dict):
            return {"proposal": proposal, "seen": seen}

        name = answer.get("tool")
        tool = tools.get(name) if isinstance(name, str) else None
        if tool is None:
            seen.append({"tool": str(name), "args": {}, "text": "no such tool"})
            continue

        args = answer.get("args") if isinstance(answer.get("args"), dict) else {}
        try:
            result = tool(**args)
        except TypeError:
            seen.append({"tool": name, "args": args, "text": "wrong arguments for this tool"})
            continue
        seen.append({"tool": name, "args": args, "text": flat(result)[:MAX_TOOL_CHARS] or "nothing found"})
        trace.current.record(f"reviewer_tool:{name}", 0, note=f"{notebook} · {json.dumps(args, ensure_ascii=False)[:60]}")

    return None


def grounded(url: str, returned: str) -> bool:
    """Whether this source is something the reviewer actually read on this run.

    A reviewer cites from memory as readily as from a page it just opened, and the two
    look identical in the answer. If the link, or the identifier at the end of it, came
    back from a tool this run, it was read. Otherwise it was remembered.
    """
    tail = re.split(r"[/#?]", str(url or "").rstrip("/"))[-1].lower()
    return flat(url) in returned or (len(tail) > 5 and tail in returned)


def check(gathered: dict, cells: list[dict]) -> dict:
    """Keep what the notebook supports: located quotes, known statuses, named techniques."""
    proposal = (gathered or {}).get("proposal") or {}
    returned = " ".join(step["text"] for step in (gathered or {}).get("seen") or [])
    teaches, dropped, recalled = [], 0, 0

    for claim in proposal.get("teaches") or []:
        if not isinstance(claim, dict):
            dropped += 1
            continue
        cell = locate(claim.get("quote"), cells)
        if cell is None:
            dropped += 1
            continue
        teaches.append({
            "technique": str(claim.get("technique") or "")[:90],
            "as_taught": str(claim.get("as_taught") or "")[:220],
            "quote": str(claim.get("quote") or "")[:220],
            "cell": cell,
            "located": True,
        })

    named = {c["technique"] for c in teaches}
    findings = []
    for finding in proposal.get("findings") or []:
        if not isinstance(finding, dict):
            dropped += 1
            continue
        technique = str(finding.get("technique") or "")[:90]
        status = str(finding.get("status") or "")
        if technique not in named or status not in STATUSES:
            dropped += 1
            continue
        sources = [s for s in (finding.get("sources") or []) if isinstance(s, dict) and s.get("url")]
        if status != "current" and not sources:
            # A claim that something moved, with nothing to read, is an opinion.
            dropped += 1
            continue
        evidence = []
        for source in sources[:3]:
            url = str(source.get("url"))[:300]
            # A date on a page nobody opened is a fact nobody checked, so it does not
            # travel. The link does: a person can open it and see for themselves.
            seen = grounded(url, returned)
            recalled += not seen
            evidence.append({"url": url, "date": str(source.get("date") or "unknown")[:10] if seen else "unknown",
                             "seen": seen})

        findings.append({
            "technique": technique,
            "status": status,
            "now": str(finding.get("now") or "")[:220],
            "instead": str(finding.get("instead") or "")[:220],
            "why1": str(finding.get("why1") or "")[:240],
            "confidence": finding.get("confidence") if finding.get("confidence") in ("high", "medium", "low") else "medium",
            "evidence": evidence,
            "basis": "read_and_judged",
        })

    return {"teaches": teaches, "findings": findings, "dropped": dropped, "recalled": recalled}


def review(path: Path, tools: dict, ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    """One notebook, read and judged, in the shape src/review.py already reads."""
    path = Path(path)
    cells = cells_of(path)
    gathered = run(path.name, cells, tools, ask=ask, max_steps=max_steps)
    if not gathered:
        return None

    kept = check(gathered, cells)
    if not kept["teaches"]:
        # Nothing it said about the notebook could be found in the notebook.
        trace.current.record("reviewer_agent", 0, ok=False, note=f"{path.name}: nothing located, dropped")
        return None

    trace.current.record("reviewer_agent", 0, note=(
        f"{path.name}: {len(kept['teaches'])} located, {len(kept['findings'])} findings, "
        f"{kept['dropped']} dropped, {kept['recalled']} sources recalled not read, "
        f"{len(gathered['seen'])} tool calls"))
    return {
        "id": f"{path.parent.name.replace(' ', '')}/{path.stem}",
        "title": path.stem,
        "week": path.parent.name,
        "notebook": f"notebooks/{path.parent.name}/{path.name}",
        "teaches": kept["teaches"],
        "findings": kept["findings"],
        "dropped": kept["dropped"],
        "recalled": kept["recalled"],
        "looked": [{"tool": s["tool"], "args": s.get("args", {})} for s in gathered["seen"]],
        "basis": "read_and_judged",
    }
