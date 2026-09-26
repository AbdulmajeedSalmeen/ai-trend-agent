"""The material review: what each course notebook teaches, which of those
techniques the field has moved past, and what to do about it.

AI reviewers, Claude agents with web research, read the notebooks and wrote
material_review/1: per notebook, the
techniques it teaches located to a cell, their findings on those techniques with
the source they read, and a proposed verdict. That file is an input, the way the
signals are, collected once outside the pipeline. It is never taken on its own
word. The rules here decide what the page may say:

- a notebook's chapter comes from the curriculum, not from the reviewer;
- replace or retire needs at least one hard finding (removed, deprecated,
  superseded or unsafe), or the verdict is lowered to revise, and says so;
- a notebook identical to another, cell for cell, is a copy: measured, retired,
  and its findings counted once, on the original;
- a finding on a cell the import check already edits never proposes a line there;
- a credential finding is counted and never located: a pointer to a key is a key;
- every count is computed from what travels, so the page cannot disagree with itself.

A method has no version to compare, so none of this is a verified claim: every
finding says read_and_judged and carries the source a person read.

The review describes the course material in detail and the repo is public, so
fixtures/material_review.json stays out of git until the course owners say
otherwise. Without it the page simply has no material view.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from src import arabic, retirements
from src.plan import chapter_order

REVIEW_PATH = Path("fixtures/material_review.json")
CURRICULUM_PATH = Path("fixtures/curriculum.json")
SCHEMA = "material_review/1"

HARD = {"removed", "deprecated", "unsafe", "superseded"}
# missing_context ranks last: it points at an absence, and nothing was published about it.
SEVERITY = {"unsafe": 0, "removed": 1, "deprecated": 2, "superseded": 3, "missing_context": 4}
CONFIDENCE = {"high": 0, "medium": 1, "low": 2}
VERDICTS = {"retire": 0, "replace": 1, "revise": 2, "keep": 3}
STATUS_EN = {"unsafe": "unsafe as taught", "removed": "removed", "deprecated": "deprecated",
             "superseded": "superseded"}
SHOWN_PER_NOTEBOOK = 4
CREDENTIAL_RE = re.compile(r"credential|api key|secret|passcode|leaked|sk-proj|hardcoded key", re.I)
DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")
DASH_RE = re.compile(r"\s*[–—]\s*")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")
LOWERED_RE = re.compile(r"lowered from (retire|replace|revise)\b")
MODEL_RE = re.compile(r"(?<![\w.-])((?:gpt|chatgpt)-[a-z0-9.\-]*[a-z0-9]|o[1-9](?:-[a-z0-9]+)*|(?:text-)?(?:davinci|babbage)-\d+)")

BASIS_EN = ("Read and judged by AI reviewers, Claude agents searching the web, with the source they read "
            "beside it. A rule then looked for every quote they gave in the notebook's cells and dropped "
            "what it could not find. This is not one of the checked claims.")


def load(path: Path = REVIEW_PATH) -> dict | None:
    if not path.exists():
        return None

    review = json.loads(path.read_text(encoding="utf-8"))

    if review.get("schema") != SCHEMA:
        raise ValueError(f"{path} is {review.get('schema')!r}, not {SCHEMA}")

    return review


def clip(text: str | None, limit: int) -> str:
    """Trim at a sentence when one ends near the limit, so a finding never stops
    mid-clause. Reviewers write with em and en dashes; this page does not."""
    text = DASH_RE.sub(", ", re.sub(r"\s+", " ", str(text or "")).strip())

    if len(text) <= limit:
        return text

    cut = text[:limit]
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))

    if stop > limit * 0.55:
        return cut[:stop + 1]

    return cut.rsplit(" ", 1)[0] + "…"


def week_of(entry: dict) -> int | None:
    if isinstance(entry.get("week_number"), int):
        return entry["week_number"]

    match = re.search(r"\d+", str(entry.get("week", "")))
    return int(match.group()) if match else None


def decide(proposed: str, statuses: set[str]) -> str:
    """The verdict the rules allow. Replace and retire need a hard finding, and
    anything but keep needs a finding at all."""
    verdict = proposed if proposed in VERDICTS else "revise"

    if verdict in ("replace", "retire") and not statuses & HARD:
        verdict = "revise"

    if verdict != "keep" and not statuses:
        verdict = "keep"

    return verdict


def proposed_verdict(entry: dict) -> str:
    """What the reviewer proposed, even where an earlier pass already lowered it and
    left a note saying from what, so the page counts that lowering too."""
    match = LOWERED_RE.match(entry.get("verdict_note") or "")
    return match.group(1) if match else entry.get("verdict", "revise")


def spelled(date: str) -> tuple[str, ...]:
    """A date the ways reviewers write one: 2026-10-23, 23 October 2026, October 23, 2026."""
    year, month, day = date.split("-")
    name = MONTHS[int(month) - 1]
    return date, f"{int(day)} {name} {year}", f"{name} {int(day)}, {year}"


def corrected(finding: dict, shutdowns: dict[str, str], read_on: str | None) -> dict:
    """A model is removed on the day its vendor shuts it down, not before. A finding
    that says removed about a model OpenAI's table schedules for a day still ahead,
    either because the technique is that model or because its own text gives that
    date, is deprecated: the primary source and the finding's own words agree on
    that, and only the label disagreed."""
    if finding.get("status") != "removed" or not read_on:
        return finding

    subject = set(MODEL_RE.findall(finding.get("technique", "")))
    text = f"{finding.get('technique', '')} {finding.get('what_changed', '')}"
    ahead = [model for model in MODEL_RE.findall(text)
             if shutdowns.get(model, "") > read_on
             and (model in subject or any(form in text for form in spelled(shutdowns[model])))]

    return {**finding, "status": "deprecated", "corrected_from": "removed"} if ahead else finding


def is_credential(finding: dict) -> bool:
    return bool(CREDENTIAL_RE.search(f"{finding.get('technique', '')} {finding.get('what_changed', '')}"))


def source_of(finding: dict) -> tuple[str | None, str | None]:
    sources = finding.get("evidence") or finding.get("sources") or [{}]
    date = str(sources[0].get("date") or "")
    return sources[0].get("url"), date if DATE_RE.fullmatch(date) else None


def compact(finding: dict, notebook: str, owned: set) -> dict:
    url, date = source_of(finding)
    return {
        "t": clip(finding.get("technique"), 70),
        "s": finding["status"],
        "c": finding.get("confidence") if finding.get("confidence") in CONFIDENCE else "medium",
        "w": clip(finding.get("what_changed"), 320),
        "r": clip(finding.get("replacement"), 210),
        "rn": finding.get("replacement_name"),
        "cell": finding.get("cell"),
        "u": url,
        "d": date,
        "own": (notebook, finding.get("cell")) in owned,
        "was": finding.get("corrected_from"),
    }


def notebook_why(verdict: str, proposed: str, found: int, hard: int, copy_of: str | None) -> tuple[str, str]:
    lowered = proposed if proposed != verdict and not copy_of else None
    arabic_text = arabic.review_notebook(verdict, found, hard, lowered, copy_of)

    if copy_of:
        return (f"Identical, cell for cell, to {copy_of}: retire it and keep the original. "
                "Its findings are counted once, on the original.", arabic_text)

    if lowered:
        return (f"The reviewer proposed {lowered}; no finding shows a method removed, deprecated, "
                f"superseded or unsafe, so the rules lowered it to {verdict}.", arabic_text)

    noun = "finding" if found == 1 else "findings"
    return (f"{found} {noun}, {hard} about a method removed, deprecated, superseded or unsafe.", arabic_text)


def course_wide(entries: list[tuple[str, str, dict]]) -> list[dict]:
    """A technique the reviewers found wanting in two or more chapters is one
    decision for the course, the same rule the import check uses for a removed name.
    Techniques are grouped by the id the reviewers gave them, so two ids for one
    technique stay apart: the count can only be low, never inflated."""
    groups = defaultdict(list)

    for chapter_id, notebook, finding in entries:
        if chapter_id and finding["status"] in HARD and finding.get("technique_id"):
            groups[finding["technique_id"]].append((chapter_id, notebook, finding))

    found = []

    for technique_id, items in groups.items():
        chapters = sorted({chapter_id for chapter_id, _, _ in items}, key=chapter_order)

        if len(chapters) < 2:
            continue

        status = min((finding["status"] for _, _, finding in items), key=SEVERITY.get)
        technique = Counter(clip(finding.get("technique"), 70) for _, _, finding in items).most_common(1)[0][0]
        notebooks = len({notebook for _, notebook, _ in items})
        found.append({
            "technique_id": technique_id,
            "technique": technique,
            "status": status,
            "chapters": chapters,
            "notebooks": notebooks,
            "act": "investigate_larger_change",
            "why": (f"{notebooks} notebooks in {len(chapters)} chapters teach {technique}, which the reviewers "
                    f"judged {STATUS_EN[status]}: one decision for the course, not an edit per notebook."),
            "why_ar": arabic.review_course_wide(technique, status, notebooks, len(chapters)),
        })

    return sorted(found, key=lambda item: (-item["notebooks"], SEVERITY[item["status"]], item["technique_id"]))


def build(review: dict, curriculum: dict, deadlines: list[dict], retirement_data: dict | None) -> dict:
    chapters = {chapter["chapter_id"]: chapter for chapter in curriculum["chapters"]}
    placed = {(chapter["week"], name): chapter["chapter_id"]
              for chapter in curriculum["chapters"] for name in chapter.get("notebooks", [])}
    owned = {(edit["notebook"], edit["cell"])
             for chapter in curriculum["chapters"] for edit in chapter.get("material_edits", [])}
    copy_of = {copy["notebook"]: Path(copy["same_as"]).name for copy in curriculum.get("copies", [])}
    shutdowns = {model: row["shutdown"] for row in (retirement_data or {}).get("retirements", [])
                 for model in row["ids"]}
    read_on = review.get("read_on")

    books, unplaced, counted = [], [], []
    tally = Counter()
    claims = {"located": 0, "dropped": 0}
    credentials = lowered = relabelled = 0
    lessons = set()

    for entry in review["notebooks"]:
        notebook = entry["notebook"]
        name = Path(notebook).name
        week = week_of(entry)
        chapter_id = placed.get((week, name))
        original = copy_of.get(notebook)
        proposed = proposed_verdict(entry)

        findings = [corrected(finding, shutdowns, read_on)
                    for finding in entry.get("findings", []) if finding.get("status") in SEVERITY]
        statuses = {finding["status"] for finding in findings}
        verdict = "retire" if original else decide(proposed, statuses)
        shown = [] if original else sorted(
            (finding for finding in findings if not is_credential(finding)),
            key=lambda finding: (SEVERITY[finding["status"]], CONFIDENCE.get(finding.get("confidence"), 1)))

        if not original:
            credentials += len(findings) - len(shown)
            lowered += verdict != proposed
            relabelled += sum(1 for finding in findings if finding.get("corrected_from"))
            claims["located"] += entry.get("located_claims", 0)
            claims["dropped"] += entry.get("unlocated_claims", 0)
            tally.update(finding["status"] for finding in shown)
            counted.extend((chapter_id, notebook, finding) for finding in shown)

            if entry.get("new_lesson"):
                lessons.add(entry["new_lesson"]["title"])

        hard = sum(1 for finding in shown if finding["status"] in HARD)
        why, why_ar = notebook_why(verdict, proposed, len(shown), hard, original)
        book = {
            "id": entry["id"],
            "file": name,
            "ch": chapter_id,
            "wk": week,
            "v": verdict,
            "proposed": proposed if verdict != proposed else None,
            "copy_of": original,
            "act": "watch" if verdict == "keep" else "update_existing_material",
            "e": entry.get("effort") if entry.get("effort") in arabic.REVIEW_EFFORT else "medium",
            "a": clip(entry.get("action"), 240),
            "n": entry["new_lesson"]["title"] if entry.get("new_lesson") and not original else None,
            "f": [compact(finding, notebook, owned) for finding in shown[:SHOWN_PER_NOTEBOOK]],
            "more": max(0, len(shown) - SHOWN_PER_NOTEBOOK),
            "found": len(shown),
            "why": why,
            "why_ar": why_ar,
        }
        (books if chapter_id else unplaced).append(book)

    by_chapter = defaultdict(list)

    for book in books:
        by_chapter[book["ch"]].append(book)

    kept = [finding for _, _, finding in counted]
    sources = retirement_data or {}

    return {
        "schema": "material_view/1",
        "read_on": review.get("read_on"),
        "basis": "read_and_judged",
        "basis_en": BASIS_EN,
        "basis_ar": arabic.REVIEW_BASIS,
        "shown": sum(len(book["f"]) for book in books + unplaced),
        "counts": {
            "notebooks": len(books) + len(unplaced),
            "verdicts": dict(Counter(book["v"] for book in books + unplaced)),
            "statuses": dict(tally),
            "located": claims["located"],
            "claims": claims["located"] + claims["dropped"],
            "dropped": claims["dropped"],
            "anchored": sum(1 for finding in kept if finding.get("cell") is not None),
            "whole_notebook": sum(1 for finding in kept if finding.get("cell") is None),
            "lowered": lowered,
            "relabelled": relabelled,
            "copies": len([book for book in books + unplaced if book["copy_of"]]),
            "lessons": len(lessons),
            "credentials": credentials,
            "owned_by_import_check": sum(1 for chapter_id, notebook, finding in counted
                                         if (notebook, finding.get("cell")) in owned),
            "undated_sources": sum(1 for finding in kept if source_of(finding)[1] is None),
            "unplaced": len(unplaced),
        },
        "deadline_source": {"url": sources.get("source", ""), "read_on": sources.get("read_on", "")},
        "deadlines": deadlines,
        "course_wide": course_wide(counted),
        "chapters": [
            {"id": chapter_id, "title": chapters[chapter_id]["title"], "week": chapters[chapter_id]["week"],
             "books": sorted(members, key=lambda book: (VERDICTS[book["v"]], book["id"]))}
            for chapter_id, members in sorted(by_chapter.items(),
                                              key=lambda item: (chapters[item[0]]["week"], chapter_order(item[0])))
        ],
        "unplaced": unplaced,
    }


def payload(path: Path = REVIEW_PATH, curriculum_path: Path = CURRICULUM_PATH,
            retirements_path: Path = retirements.RETIREMENTS_PATH) -> dict | None:
    """The material view the page shows, or None when there is no review on this machine."""
    review = load(path)

    if review is None:
        return None

    curriculum = json.loads(curriculum_path.read_text(encoding="utf-8"))
    data = retirements.load(retirements_path)
    left_out = {copy["notebook"] for copy in curriculum.get("copies", [])}
    deadlines = retirements.deadlines(curriculum.get("model_calls", []), data, left_out)
    return build(review, curriculum, deadlines, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the rules to the material review and say what they changed.")
    parser.add_argument("--review", default=str(REVIEW_PATH))
    args = parser.parse_args()

    view = payload(Path(args.review))

    if view is None:
        raise SystemExit(f"no review at {args.review}")

    counts = view["counts"]
    print(f"{counts['notebooks']} notebooks read on {view['read_on']}: {counts['verdicts']}")
    print(f"findings {sum(counts['statuses'].values())}: {counts['statuses']}; "
          f"{counts['anchored']} at a cell, {counts['whole_notebook']} about a whole notebook")
    print(f"claims located {counts['located']} of {counts['claims']}, dropped {counts['dropped']}")
    print(f"lowered {counts['lowered']}, relabelled removed to deprecated {counts['relabelled']}, "
          f"copies {counts['copies']}, credentials withheld {counts['credentials']}, "
          f"on cells the import check owns {counts['owned_by_import_check']}, undated sources {counts['undated_sources']}")

    for book in view["unplaced"]:
        print(f"  no chapter: {book['file']}")

    for item in view["course_wide"]:
        print(f"  course-wide: {item['technique']} ({item['status']}) in {item['notebooks']} notebooks, "
              f"{', '.join(item['chapters'])}")

    for deadline in view["deadlines"]:
        print(f"  {deadline['date']}: {deadline['books']} notebooks, {deadline['what']}")


if __name__ == "__main__":
    main()
