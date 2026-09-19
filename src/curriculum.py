import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from src.notebooks import NOTEBOOK_DIR, scan_all

CURRICULUM_PATH = Path("fixtures/curriculum.json")

STOP_WORDS = {
    "demo", "exercise", "lab", "solution", "sol", "sample", "new", "version",
    "intro", "using", "your", "the", "for", "with", "and", "build", "implement",
    "ver", "part", "final", "copy",
}


def words(text: str) -> set[str]:
    found = re.findall(r"[a-z0-9]+", text.lower())

    return {word for word in found if word not in STOP_WORDS and len(word) > 2}


def squashed(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def chapter_text(chapter: dict) -> str:
    return " ".join(chapter["topics_covered"] + [chapter["title"]] + chapter.get("tools_covered", []))


def week_of(report: dict) -> int | None:
    match = re.search(r"\d+", report["week"])

    return int(match.group()) if match else None


def assign(report: dict, chapters: list[dict]) -> str | None:
    week = week_of(report)
    candidates = [c for c in chapters if c["week"] == week]

    if not candidates:
        return None

    name = words(Path(report["file"]).stem)
    best, best_score = None, 0

    for chapter in candidates:
        score = len(name & words(chapter_text(chapter)))

        if score > best_score:
            best, best_score = chapter["chapter_id"], score

    if best is not None:
        return best

    flat = squashed(Path(report["file"]).stem)

    for chapter in candidates:
        for tool in chapter.get("tools_covered", []):
            if squashed(tool) and squashed(tool) in flat:
                return chapter["chapter_id"]

    return None


def collect(reports: list[dict], chapters: list[dict]) -> dict:
    grouped = defaultdict(lambda: {"specs": defaultdict(Counter), "unpinned": Counter(),
                                   "legacy": {}, "files": []})

    for report in reports:
        chapter_id = assign(report, chapters)

        if chapter_id is None:
            continue

        entry = grouped[chapter_id]
        entry["files"].append(report["file"])

        for package, spec in report["pinned"].items():
            entry["specs"][package][spec] += 1

        for package in report["unpinned"]:
            entry["unpinned"][package] += 1

        for pattern in report["patterns"]:
            if pattern["legacy"]:
                entry["legacy"][pattern["uses"]] = (pattern["package"], pattern["note"])

    return grouped


def apply(chapters: list[dict], grouped: dict) -> None:
    for chapter in chapters:
        entry = grouped.get(chapter["chapter_id"])

        if entry is None:
            continue

        chapter["pins"] = {package: counts.most_common(1)[0][0]
                           for package, counts in sorted(entry["specs"].items())}
        chapter["installs_unpinned"] = sorted(entry["unpinned"])
        chapter["legacy_api"] = [{"package": package, "uses": uses, "note": note}
                                 for uses, (package, note) in sorted(entry["legacy"].items())]
        chapter["notebooks"] = sorted(entry["files"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the course notebooks into the curriculum file.")
    parser.add_argument("--notebooks", default=str(NOTEBOOK_DIR))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    chapters = data["chapters"]
    reports = scan_all(Path(args.notebooks))
    grouped = collect(reports, chapters)

    unplaced = [r["file"] for r in reports if assign(r, chapters) is None]
    apply(chapters, grouped)

    data["pins_note"] = (
        "pins, installs_unpinned and legacy_api are read from the course notebooks by "
        "`python -m src.curriculum`. A package under installs_unpinned has no version bound in the "
        "notebook, so a student installs whatever is newest on the day they run it."
    )

    if not args.dry_run:
        CURRICULUM_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for chapter in chapters:
        if not chapter.get("notebooks"):
            continue

        print(f"\n{chapter['chapter_id']}  {len(chapter['notebooks'])} notebooks")

        for package, spec in chapter["pins"].items():
            print(f"  runs      {package} {spec}")

        if chapter["installs_unpinned"]:
            print(f"  unpinned  {', '.join(chapter['installs_unpinned'])}")

        for legacy in chapter["legacy_api"]:
            print(f"  legacy    {legacy['uses']} - {legacy['note']}")

    if unplaced:
        print("\nnot placed in any chapter:")
        for name in unplaced:
            print(f"  {name}")


if __name__ == "__main__":
    main()
