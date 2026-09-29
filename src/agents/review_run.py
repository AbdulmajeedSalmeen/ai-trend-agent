"""Run the reviewer over the course and write the file the rules already read.

The reviewer agent judges one notebook. This drives it across all of them and writes
material_review/1, the same artifact src/review.py has always consumed, so nothing
downstream changes: the rules still place each notebook in its chapter, still lower a
replacement that rests on an absence, still count a copy once, and still refuse to call
any of it verified.

It is a collector, like stage 1: it reads the course from disk and may ask arXiv, and
so may the lesson and worth agents it drives. (The verifier in stage 2b reaches the
registries too; this is not the only agent with the network.) It resumes, because 89
notebooks at several model calls each is not something to start from the beginning
twice, and it writes after every notebook so a run that dies keeps what it learned.

It writes beside the review the page reads, never over it. fixtures/material_review.json
came from another process, covers more, and is what the page serves; replacing it is a
decision made with --replace, not a default. A file this driver did not write, or one it
cannot read, is left exactly as it is, and a run that reads nothing new writes nothing.

The output describes the course in detail, so the file it writes is gitignored and stays
on the machine that ran it.
"""

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path

from src import runio
from src.agents import evidence, lesson, placement, reviewer, worth
from src.notebooks import NOTEBOOK_DIR
from src.review import AGENT_SOURCE
from src.sources import arxiv

OUT_PATH = Path("fixtures/material_review.agent.json")
SERVED_PATH = Path("fixtures/material_review.json")
SCHEMA = "material_review/1"
SOURCE = AGENT_SOURCE
HARD = {"removed", "deprecated", "unsafe", "superseded"}


# A name written as code: create_agent, langchain_classic.chains, ChatOpenAI.
CODE_NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")


def code_name(text) -> str | None:
    """The first thing in a suggestion that is a name in code, or None.

    "create_agent, which keeps the loop" names create_agent, and "Use create_agent" does
    too; the first word made those "create_agent," and "Use", and the course-wide count
    tallied them as what to teach instead. A snake_case or dotted name is taken before a
    CamelCase one, and prose that names no code names nothing.
    """
    words = CODE_NAME.findall(str(text or ""))

    def dotted(word: str) -> bool:
        return ("_" in word or "." in word) and all(len(part) > 1 for part in word.split("."))

    return next((word for word in words if dotted(word)), None) or next(
        (word for word in words if re.search(r"[a-z][A-Z]", word)), None)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:48]


def newest_run() -> Path | None:
    runs = sorted(Path(runio.RUNS_DIR).glob("run_*")) if Path(runio.RUNS_DIR).exists() else []
    return runs[-1] if runs else None


def entry_for_page(entry: dict, written: dict | None = None,
                   placed: dict | None = None, weighed: dict | None = None) -> dict:
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
            "replacement_name": code_name(finding["instead"]),
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
        # Effort was this word, written once, for all eighty-nine entries. It is now
        # what the judge said after reading how far the technique reaches, and the word
        # again only when there was nothing it could stand behind.
        "effort": weighed["effort"] if weighed else "medium",
        "effort_source": "judged" if weighed else "default",
        # Worth is what a teacher loses by leaving it alone, which severity cannot say.
        # The page still orders by verdict; this is here for the day it orders by more.
        "worth": weighed["worth"] if weighed else None,
        "worth_why": weighed["reason"] if weighed else None,
        "worth_cites": weighed["cites"] if weighed else [],
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
        # A lesson that does not exist yet is in no chapter's topic list, so nothing
        # could place it. It owns a chapter when that chapter already carries the name,
        # and otherwise it follows one, which is still a week and an order.
        "lesson_place": ({"relation": placed["relation"], "chapter": placed["chapter"],
                          "week": placed["week"], "why": placed["why"]} if placed else None),
        "basis": "read_and_judged",
    }


def tools_for(path: Path, run_dir: Path | None, research: bool) -> dict:
    cells = reviewer.cells_of(path)
    kit = {"read_cells": reviewer.read_cells_tool(cells)}
    kit["release_notes"] = (evidence.release_notes_tool(run_dir) if run_dir
                            else lambda package="": "this run collected no releases")
    kit["papers"] = reviewer.papers_tool((lambda term: arxiv.search(term)) if research else None)
    return kit


def chapters_of(path: Path) -> list[dict]:
    """The course's chapters, or none, in which case nothing is placed."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))["chapters"]
    except (OSError, KeyError, json.JSONDecodeError):
        return []


def lesson_tools(entry: dict, notebook_dir: Path, research: bool) -> dict:
    papers = reviewer.papers_tool((lambda term: arxiv.search(term)) if research else None)
    return lesson.tools_for(entry, course_uses=evidence.course_uses_tool(notebook_dir),
                            papers=lambda term: papers(term=term))


def worth_tools(entry: dict, notebook_dir: Path, research: bool) -> dict:
    papers = reviewer.papers_tool((lambda term: arxiv.search(term)) if research else None)
    return worth.tools_for(lesson.findings_tool(entry),
                           course_uses=evidence.course_uses_tool(notebook_dir),
                           papers=lambda term: papers(term=term))


def load_existing(out_path: Path, replace: bool = False) -> dict:
    """What an earlier run of this driver wrote, so a rerun resumes where it stopped.

    A file it cannot read, or one something else wrote, is never taken as empty, because
    the next write would replace it. With replace, a file something else wrote is
    started over, which is what replace means.
    """
    if not out_path.exists():
        return {}

    try:
        old = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit(f"{out_path} cannot be read, so it is left as it is. "
                         f"Move it aside to start again.")

    ours = isinstance(old, dict) and old.get("source") == SOURCE

    if not ours and not replace:
        said = old.get("source") if isinstance(old, dict) else None
        raise SystemExit(f"{out_path} was not written by this driver (source: {said!r}), so it is left "
                         f"as it is. Pass --replace to write over it.")

    return {entry["notebook"]: entry for entry in old.get("notebooks", [])} if ours else {}


def write(out_path: Path, entries: dict) -> None:
    notebooks = list(entries.values())
    payload = {
        "schema": SCHEMA,
        "read_on": date.today().isoformat(),
        "source": SOURCE,
        "counts": {
            "notebooks_reviewed": len(notebooks),
            "claims_located_in_a_cell": sum(n["located_claims"] for n in notebooks),
            "claims_dropped_as_unfound": sum(n["unlocated_claims"] for n in notebooks),
            "sources_recalled_not_read": sum(n.get("recalled_sources", 0) for n in notebooks),
            "lessons_written": sum(1 for n in notebooks if n.get("new_lesson")),
            "effort_judged_not_assumed": sum(1 for n in notebooks if n.get("effort_source") == "judged"),
        },
        "notebooks": notebooks,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Written aside and moved into place, so a run killed mid-write leaves the last
    # good file rather than half of one.
    partial = out_path.with_name(out_path.name + ".tmp")
    partial.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(partial, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the course notebooks with the reviewer agent.")
    parser.add_argument("--notebooks", default=str(NOTEBOOK_DIR))
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--limit", type=int, default=0, help="stop after this many notebooks")
    parser.add_argument("--only", default="", help="review only notebooks whose name contains this")
    parser.add_argument("--again", action="store_true",
                        help="review again the notebooks already in the file; the others are kept")
    parser.add_argument("--replace", action="store_true",
                        help="write over a file this driver did not write, such as the review the page reads")
    parser.add_argument("--no-research", action="store_true", help="do not ask arXiv")
    parser.add_argument("--no-lessons", action="store_true", help="do not write a lesson for each notebook")
    parser.add_argument("--curriculum", default="fixtures/curriculum.json",
                        help="the chapters a written lesson is placed against")
    args = parser.parse_args()

    out_path = Path(args.out)
    entries = load_existing(out_path, replace=args.replace)
    run_dir = newest_run()
    chapters = chapters_of(args.curriculum)
    place_kit = placement.tools_for(chapters, course_uses=evidence.course_uses_tool(Path(args.notebooks)))
    paths = [p for p in sorted(Path(args.notebooks).glob("*/*.ipynb")) if args.only.lower() in p.name.lower()]
    done = 0

    for path in paths:
        key = f"notebooks/{path.parent.name}/{path.name}"
        if key in entries and not args.again:
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
        placed = (placement.place(written["term"], written["why"], chapters, place_kit)
                  if written and chapters else None)
        weighed = worth.judge(entry, worth_tools(entry, Path(args.notebooks), research))
        entries[key] = entry_for_page(entry, written, placed, weighed)
        done += 1
        write(out_path, entries)
        print(f"read: {path.name} | {entries[key]['located_claims']} located | "
              f"{len(entries[key]['findings'])} findings | {entries[key]['verdict']}"
              + (f" | {weighed['worth']}/5 {weighed['effort']}" if weighed else "")
              + (f" | lesson: {written['title'][:46]}" if written else "")
              + (f" | {placed['relation']} {placed['chapter']}" if placed else ""))

    if done:
        print(f"{len(entries)} notebooks in {out_path}")
    else:
        print(f"nothing new was read; {out_path} is left as it was")


if __name__ == "__main__":
    main()
