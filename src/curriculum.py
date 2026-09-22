import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from src import material
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


def tracked_packages(path: Path = CURRICULUM_PATH) -> list[str]:
    """Every package the course installs, pinned or not. This is the watchlist:
    the agent follows what the material actually depends on, not a list we typed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    found: set[str] = set()

    for chapter in data["chapters"]:
        found.update(chapter.get("pins", {}))
        found.update(chapter.get("installs_unpinned", []))

    return sorted(found)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the course notebooks into the curriculum file.")
    parser.add_argument("--notebooks", default=str(NOTEBOOK_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offline", action="store_true",
                        help="do not read releases; keep the material edits already in the file")
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

    if not args.offline:
        root = Path(args.notebooks)
        files = sorted(root.rglob("*.ipynb")) if root.is_dir() else [root]
        found = material.check_all(files, lambda path: assign({"file": path.name, "week": path.parent.name},
                                                              chapters), material.releases_now())

        for chapter in chapters:
            chapter["material_edits"] = found["edits"].get(chapter["chapter_id"], [])

        data["material_checked"] = found["checked"]
        data["material_note"] = (
            "material_edits are read by `python -m src.curriculum`: every langchain import in the "
            "notebooks, checked against the source of the newest release at its tag on GitHub, with the "
            "replacement found the same way. runs_as_pinned is true when the notebook's own pin keeps it "
            "on the old line, so the edit is for the day the course moves, not a break today."
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

        edits = chapter.get("material_edits", [])

        if edits:
            breaking = sum(1 for edit in edits if edit["runs_as_pinned"] is False)
            print(f"  edits     {len(edits)} lines in {len({edit['notebook'] for edit in edits})} notebooks, "
                  f"{breaking} break on today's install")

    if unplaced:
        print("\nnot placed in any chapter:")
        for name in unplaced:
            print(f"  {name}")


if __name__ == "__main__":
    main()
