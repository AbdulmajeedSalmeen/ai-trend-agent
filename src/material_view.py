"""The course material, notebook by notebook and cell by cell: what to change,
and the evidence for each change.

Three kinds of evidence meet here, and each keeps its own label:

- import: a line a notebook imports that the release a student installs today no
  longer has, with the line to write instead, both read from the release source
  at its tag (src/material.py). Verified.
- model: a cell that names a model, or calls a LangChain constructor whose
  default is one, that OpenAI has scheduled to shut down, read from its own
  deprecations table (src/retirements.py). Verified.
- method: a technique the AI reviewers judged removed, deprecated, superseded,
  unsafe or missing today's context, located to its cell by rule (src/review.py).
  Read and judged, never verified.

The first two are facts already public in fixtures/curriculum.json, so this view
always exists and a committed page can carry it. The third describes the course
in detail and joins only when the review is on this machine and the build asks
for it.
"""
import json
from collections import defaultdict
from pathlib import Path

from src import arabic, lessons, retirements, review
from src.plan import chapter_order

VERIFIED_EN = ("Verified by rule: an import against the source of the release a student installs today, "
               "a model against OpenAI's own deprecations table.")
KIND_ORDER = {"import": 0, "model": 1, "method": 2}
# The card reads a notebook's changes from its cells, so the review's own short list
# of findings (f) and what each model run offered (offered) stay out of the page.
REVIEW_FIELDS = ("v", "proposed", "copy_of", "act", "e", "a", "n", "more", "found", "why", "why_ar", "ld")


def notebook_path(week: int, name: str) -> str:
    return f"notebooks/week {week}/{name}"


def import_item(edit: dict) -> dict:
    return {"kind": "import", "basis": "verified", "now": edit.get("current"), "instead": edit.get("proposed"),
            "why1": edit.get("reason"), "current": edit.get("current"), "proposed": edit.get("proposed"),
            "names": edit.get("names", []), "why": edit.get("reason"), "why_ar": edit.get("reason_ar"),
            "u": edit.get("evidence_url"), "checked": edit.get("checked"), "breaks": edit.get("runs_as_pinned") is False,
            "agree": 0}


def model_item(call: dict, row: dict, cell: int, source: dict) -> dict:
    model, shutdown, replacement = call["model"], row["shutdown"], row["replacement"]
    past = bool(source.get("read_on")) and shutdown < source["read_on"]
    stops = "shut it down" if past else "shuts it down"

    if call["how"] == "named":
        english = (f"Cell {cell} names {model}. OpenAI {stops} on {shutdown} and names {replacement} "
                   "to use instead.")
    else:
        english = (f"Cell {cell} calls LangChain's {call['constructor']}() with no model, which defaults to "
                   f"{model}. OpenAI {stops} on {shutdown} and names {replacement} to use instead.")

    now = model if call["how"] == "named" else f"{call['constructor']}() with no model, so {model}"

    return {"kind": "model", "basis": "verified", "now": now, "instead": replacement,
            "why1": f"OpenAI {'shut' if past else 'shuts'} {model} down on {shutdown}.", "agree": 0,
            "model": model, "how": call["how"],
            "constructor": call.get("constructor"), "shutdown": shutdown, "replacement": replacement,
            "u": source.get("source"), "d": source.get("read_on"), "why": english,
            "why_ar": arabic.model_cell(cell, model, call["how"], call.get("constructor"), shutdown, replacement,
                                        past)}


def method_item(finding: dict) -> dict:
    return {"kind": "method", "basis": "read_and_judged",
            **{key: value for key, value in finding.items() if key != "cell"}}


def restates(finding: dict, verified: dict) -> bool:
    """A reviewer finding that says what a verified change in the same cell already
    says, naming its model or one of its imported names, adds nothing but a second
    voice. It is kept, marked, and counted on the verified change as agreement. Only a
    finding that something is going away can restate one: an unsafe or superseded
    finding that mentions the same class is saying something else about it."""
    if finding.get("s") not in ("removed", "deprecated"):
        return False

    text = " ".join(str(finding.get(key) or "") for key in ("t", "now", "w", "why1"))
    marks = [verified["model"]] if verified["kind"] == "model" else verified.get("names") or []
    return any(mark and mark in text for mark in marks)


def item_order(item: dict) -> tuple:
    return KIND_ORDER[item["kind"]], review.SEVERITY.get(item.get("s"), 9)


def cells_of(path: str, edits: dict, calls: dict, rows: dict, source: dict,
             findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Every cell with something to change, in cell order, and the judged findings
    about the notebook as a whole."""
    cells = defaultdict(list)

    for edit in edits.get(path, []):
        cells[edit["cell"]].append(import_item(edit))

    seen = set()

    for call in calls.get(path, []):
        row = rows.get(call["model"])
        key = (call["cell"], call["model"], call["how"])

        if row is None or key in seen:
            continue

        seen.add(key)
        cells[call["cell"]].append(model_item(call, row, call["cell"], source))

    whole = []

    for finding in findings:
        if finding.get("cell") is None:
            whole.append(method_item(finding))
        else:
            cells[finding["cell"]].append(method_item(finding))

    for items in cells.values():
        checked = [item for item in items if item["basis"] == "verified"]

        for item in items:
            if item["kind"] != "method":
                continue

            same = next((verified for verified in checked if restates(item, verified)), None)
            item["dup"] = same["kind"] if same else None

            if same:
                same["agree"] += 1

    return [{"cell": cell, "items": sorted(items, key=item_order)} for cell, items in sorted(cells.items())], whole


def without_offered(lesson: dict | None) -> dict | None:
    return {key: value for key, value in lesson.items() if key != "offered"} if lesson else lesson


def blank_book(chapter: dict, name: str, copy_of: str | None) -> dict:
    """A notebook as the curriculum knows it, before any review."""
    return {"id": f"week{chapter['week']}/{Path(name).stem}", "file": name, "ch": chapter["chapter_id"],
            "wk": chapter["week"], "v": None, "proposed": None, "copy_of": copy_of, "act": None, "e": None,
            "a": "", "n": None, "more": 0, "found": 0, "why": "", "why_ar": "", "ld": None}


def unreviewed_counts(notebooks: int, copies: int) -> dict:
    """The review's counts, all zero, so a page written for the reviewed view reads
    the verified one without a missing key."""
    zero = ("located", "claims", "dropped", "anchored", "whole_notebook", "lowered", "relabelled", "lessons",
            "credentials", "owned_by_import_check", "undated_sources", "unplaced", "lessons_measured",
            "lessons_new", "lessons_optional", "lessons_watch")
    return {"notebooks": notebooks, "verdicts": {}, "statuses": {}, "copies": copies, **dict.fromkeys(zero, 0)}


def view(curriculum: dict, data: dict | None, deadlines: list[dict], reviewed: dict | None) -> dict:
    """The material view: every notebook the curriculum holds, with its cells to change.
    `reviewed` is review.build's output, or None for the verified view alone."""
    edits = defaultdict(list)

    for chapter in curriculum["chapters"]:
        for edit in chapter.get("material_edits", []):
            edits[edit["notebook"]].append(edit)

    calls = {entry["notebook"]: entry["calls"] for entry in curriculum.get("model_calls", [])}
    rows = {model: row for row in (data or {}).get("retirements", []) for model in row["ids"]}
    source = {"source": (data or {}).get("source"), "read_on": (data or {}).get("read_on")}
    copies = {copy["notebook"]: Path(copy["same_as"]).name for copy in curriculum.get("copies", [])}
    judged = {(book["wk"], book["file"]): book
              for chapter in (reviewed or {}).get("chapters", []) for book in chapter["books"]}
    chapters_out, books_all = [], []

    for chapter in sorted(curriculum["chapters"], key=lambda c: (c["week"], chapter_order(c["chapter_id"]))):
        members = []

        for name in chapter.get("notebooks", []):
            path = notebook_path(chapter["week"], name)
            base = blank_book(chapter, name, copies.get(path))
            found = judged.get((chapter["week"], name))

            if found:
                base.update({key: found[key] for key in REVIEW_FIELDS if key in found})
                base["ld"] = without_offered(base["ld"])

            if base["copy_of"]:
                cells, whole = [], []
            else:
                cells, whole = cells_of(path, edits, calls, rows, source, (found or {}).get("all", []))

            members.append({**base, "cells": cells, "whole": whole, "changes": len(cells)})

        if not members:
            continue

        if reviewed:
            members.sort(key=lambda book: (review.VERDICTS.get(book["v"], 9), book["id"]))
        else:
            members.sort(key=lambda book: (-book["changes"], book["file"]))

        books_all.extend(members)
        chapters_out.append({"id": chapter["chapter_id"], "title": chapter["title"], "week": chapter["week"],
                             "books": members})

    kept = [book for book in books_all if not book["copy_of"]]
    every_cell = [cell for book in kept for cell in book["cells"]]
    verified = [cell for cell in every_cell if any(item["basis"] == "verified" for item in cell["items"])]

    return {
        "schema": "material_view/2",
        "reviewed": reviewed is not None,
        "summary": {
            "notebooks": len(books_all),
            "notebooks_to_change": sum(1 for book in kept
                                       if book["cells"] or book["whole"] or book["v"] in ("revise", "replace", "retire")),
            "cells": len(every_cell),
            "cells_verified": len(verified),
            "cells_judged": len(every_cell) - len(verified),
            "breaks_today": sum(1 for cell in every_cell for item in cell["items"] if item.get("breaks")),
            "stop_running": [{"date": deadline["date"], "notebooks": deadline["books"]} for deadline in deadlines],
            "copies": len(books_all) - len(kept),
        },
        "verified_en": VERIFIED_EN,
        "verified_ar": arabic.VERIFIED,
        "read_on": (reviewed or {}).get("read_on"),
        "basis": "read_and_judged",
        "basis_en": review.BASIS_EN,
        "basis_ar": arabic.REVIEW_BASIS,
        "shown": (reviewed or {}).get("shown", 0),
        "counts": (reviewed or {}).get("counts") or unreviewed_counts(len(books_all), len(books_all) - len(kept)),
        "lessons_checked": (reviewed or {}).get("lessons_checked"),
        "lessons": [without_offered(lesson) for lesson in (reviewed or {}).get("lessons", [])],
        "course_wide": (reviewed or {}).get("course_wide", []),
        "deadline_source": {"url": source["source"] or "", "read_on": source["read_on"] or ""},
        "deadlines": deadlines,
        "chapters": chapters_out,
        "unplaced": (reviewed or {}).get("unplaced", []),
    }


def payload(include_review: bool = True, review_path: Path = review.REVIEW_PATH,
            curriculum_path: Path = review.CURRICULUM_PATH,
            retirements_path: Path = retirements.RETIREMENTS_PATH,
            demand_path: Path = lessons.DEMAND_PATH) -> dict:
    """The view the page opens on. With include_review off, or no review on this
    machine, it holds the verified changes alone and is safe to commit."""
    curriculum = json.loads(curriculum_path.read_text(encoding="utf-8"))
    data = retirements.load(retirements_path)
    left_out = {copy["notebook"] for copy in curriculum.get("copies", [])}
    deadlines = retirements.deadlines(curriculum.get("model_calls", []), data, left_out)
    reviewed = None

    if include_review:
        material = review.load(review_path)

        if material is not None:
            demand = json.loads(demand_path.read_text(encoding="utf-8")) if demand_path.exists() else None
            reviewed = review.build(material, curriculum, deadlines, data, demand)

    return view(curriculum, data, deadlines, reviewed)
