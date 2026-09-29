"""Run the reviewer over the course and write the file the rules already read.

The reviewer agent judges one notebook. This drives it across all of them and writes
material_review/1, the same artifact src/review.py has always consumed, so nothing
downstream changes: the rules still place each notebook in its chapter, still lower a
replacement that rests on an absence, still count a copy once, and still refuse to call
any of it verified.

It is a collector, like stage 1: it reads the course from disk and may ask arXiv, and
it is the only agent allowed to reach the network. It resumes, because 89 notebooks at
several model calls each is not something to start from the beginning twice, and it
writes after every notebook so a run that dies keeps what it learned.

The output describes the course in detail and the repository is public, so the file it
writes is gitignored and stays on the machine that ran it.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

from src import runio
from src.agents import evidence, lesson, reviewer
from src.notebooks import NOTEBOOK_DIR
from src.sources import arxiv

OUT_PATH = Path("fixtures/material_review.json")
SCHEMA = "material_review/1"
HARD = {"removed", "deprecated", "unsafe", "superseded"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:48]


def newest_run() -> Path | None:
    runs = sorted(Path(runio.RUNS_DIR).glob("run_*")) if Path(runio.RUNS_DIR).exists() else []
    return runs[-1] if runs else None


def entry_for_page(entry: dict, written: dict | None = None) -> dict:
    """The agent's answer, in the shape the rules read.

    The agent speaks in pairs: what the notebook does now, what to teach instead. The
    rules were written for a reviewer's prose, so each finding carries both spellings
    and the technique it belongs to, located to its cell.
    """
    by_technique = {claim["technique"]: claim for claim in entry["teaches"]}
    teaches = [{**claim, "technique_id": slug(claim["technique"])} for claim in entry["teaches"]]

    findings = []
    for finding in entry["findings"]:
        claim = by_technique.get(finding["technique"], {})
        findings.append({
            "technique": finding["technique"],
            "technique_id": slug(finding["technique"]),
            "status": finding["status"],
            "what_changed": finding["why1"],
            "replacement": finding["instead"],
            "replacement_name": finding["instead"].split()[0] if finding["instead"] else None,
            "confidence": finding["confidence"],
            "evidence": finding["evidence"],
            "cell": claim.get("cell"),
            "basis": "read_and_judged",
        })

    # A lesson the agent called current is not something to change, so it proposes
    # nothing on its own. Only a finding that says the field moved asks for work.
    moved = [f for f in findings if f["status"] != "current"]
    statuses = {f["status"] for f in moved}
    proposed = "replace" if statuses & HARD else ("revise" if moved else "keep")
    first = next((f for f in moved if f.get("cell") and f["replacement"]), None)
    action = (f"Cell {first['cell']}: {first['replacement']}." if first
              else "Nothing to change: what it teaches is still how the field does it.")

    return {
        "id": entry["id"],
        "title": entry["title"],
        "week": entry["week"],
        "notebook": entry["notebook"],
        "verdict": proposed,
        "effort": "medium",
        "action": action,
        "teaches": teaches,
        "findings": findings,
        "located_claims": len(teaches),
        "unlocated_claims": entry["dropped"],
        "recalled_sources": entry.get("recalled", 0),
        "looked": entry["looked"],
        # The reviewer says what moved; the lesson agent says what to teach instead.
        # src/lessons.py measures whether employers ask for it, and the rules there
        # decide whether it becomes a lesson, optional content, or something to watch.
        "new_lesson": ({"title": written["title"], "why": written["why"], "covers": written["covers"]}
                       if written else None),
        "lesson_term": written["term"] if written else None,
        "lesson_answers": written["answers"] if written else [],
        "basis": "read_and_judged",
    }


def tools_for(path: Path, run_dir: Path | None, research: bool) -> dict:
    cells = reviewer.cells_of(path)
    kit = {"read_cells": reviewer.read_cells_tool(cells)}
    kit["release_notes"] = (evidence.release_notes_tool(run_dir) if run_dir
                            else lambda package="": "this run collected no releases")
    kit["papers"] = reviewer.papers_tool((lambda term: arxiv.search(term)) if research else None)
    return kit


def lesson_tools(entry: dict, notebook_dir: Path, research: bool) -> dict:
    papers = reviewer.papers_tool((lambda term: arxiv.search(term)) if research else None)
    return lesson.tools_for(entry, course_uses=evidence.course_uses_tool(notebook_dir),
                            papers=lambda term: papers(term=term))


def load_existing(out_path: Path) -> dict:
    if not out_path.exists():
        return {}
    try:
        old = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {entry["notebook"]: entry for entry in old.get("notebooks", [])}


def write(out_path: Path, entries: dict) -> None:
    notebooks = list(entries.values())
    payload = {
        "schema": SCHEMA,
        "read_on": date.today().isoformat(),
        "source": "the course notebooks, read by the reviewer agent",
        "counts": {
            "notebooks_reviewed": len(notebooks),
            "claims_located_in_a_cell": sum(n["located_claims"] for n in notebooks),
            "claims_dropped_as_unfound": sum(n["unlocated_claims"] for n in notebooks),
            "sources_recalled_not_read": sum(n.get("recalled_sources", 0) for n in notebooks),
            "lessons_written": sum(1 for n in notebooks if n.get("new_lesson")),
        },
        "notebooks": notebooks,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the course notebooks with the reviewer agent.")
    parser.add_argument("--notebooks", default=str(NOTEBOOK_DIR))
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--limit", type=int, default=0, help="stop after this many notebooks")
    parser.add_argument("--only", default="", help="review only notebooks whose name contains this")
    parser.add_argument("--again", action="store_true", help="review notebooks already in the file")
    parser.add_argument("--no-research", action="store_true", help="do not ask arXiv")
    parser.add_argument("--no-lessons", action="store_true", help="do not write a lesson for each notebook")
    args = parser.parse_args()

    out_path = Path(args.out)
    entries = {} if args.again else load_existing(out_path)
    run_dir = newest_run()
    paths = [p for p in sorted(Path(args.notebooks).glob("*/*.ipynb")) if args.only.lower() in p.name.lower()]
    done = 0

    for path in paths:
        key = f"notebooks/{path.parent.name}/{path.name}"
        if key in entries:
            continue
        if args.limit and done >= args.limit:
            break
        research = not args.no_research
        entry = reviewer.review(path, tools_for(path, run_dir, research))
        if entry is None:
            print(f"read: {path.name} | nothing located, left out")
            continue
        written = (None if args.no_lessons
                   else lesson.propose(entry, lesson_tools(entry, Path(args.notebooks), research),
                                       count=lambda term: lesson.taught_in(term, Path(args.notebooks))))
        entries[key] = entry_for_page(entry, written)
        done += 1
        write(out_path, entries)
        print(f"read: {path.name} | {entries[key]['located_claims']} located | "
              f"{len(entries[key]['findings'])} findings | {entries[key]['verdict']}"
              + (f" | lesson: {written['title'][:50]}" if written else ""))

    write(out_path, entries)
    print(f"{len(entries)} notebooks in {out_path}")


if __name__ == "__main__":
    main()
