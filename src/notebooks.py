import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

NOTEBOOK_DIR = Path("notebooks")

PIP_LINE_RE = re.compile(r"^\s*[!%]?\s*(?:\S+\s+-m\s+)?(?:pip|pip3|uv pip)\s+install\b(.*)$")
TOKEN_RE = re.compile(r"""["']([^"']+)["']|(\S+)""")
REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*(.*)$")
BOUND_RE = re.compile(r"(\d+(?:\.\d+)*)")

SKIP_TOKENS = {"install", "pip", "pip3", "-r", "requirements.txt", "/dev/null"}

# " (1)", " (2)": the number a browser adds when the same file is saved twice.
COPY_SUFFIX_RE = re.compile(r"\s\(\d+\)$")

PATTERNS = {
    # What the notebooks import from langchain is checked against the release
    # itself by src/material.py. Matching names here called RetrievalQA removed
    # when a notebook already imported it from langchain_classic, where it works.
    "langchain": [
        ("create_retrieval_chain", "create_retrieval_chain", "current"),
        ("create_react_agent", "create_react_agent", "current"),
    ],
    "openai": [
        ("openai.ChatCompletion", "openai.ChatCompletion", "removed in openai 1.x"),
        ("openai.Completion", "openai.Completion", "removed in openai 1.x"),
        ("client.chat.completions", "client.chat.completions", "current"),
    ],
    "transformers": [
        ("AutoModelFor", "Auto classes", "current"),
        ("Trainer(", "Trainer", "current"),
        ("pipeline(", "the pipeline helper", "current"),
    ],
    "langgraph": [
        ("MessageGraph", "MessageGraph", "removed in langgraph 0.3"),
        ("StateGraph", "StateGraph", "current"),
    ],
}


def code_cells(notebook: dict) -> list[str]:
    sources = []

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", "")
        sources.append("".join(source) if isinstance(source, list) else source)

    return sources


def requirements(line: str) -> list[tuple[str, str]]:
    match = PIP_LINE_RE.match(line)

    if match is None:
        return []

    found = []
    arguments = match.group(1).split("#")[0]

    for quoted, bare in TOKEN_RE.findall(arguments):
        token = quoted or bare

        if token.startswith("-") or token in SKIP_TOKENS or token.startswith(">"):
            continue

        parsed = REQUIREMENT_RE.match(token)

        if parsed is None:
            continue

        found.append((parsed.group(1).lower().replace("_", "-"), parsed.group(2).strip()))

    return found


def clean_spec(spec: str) -> str | None:
    """The version bound as the notebook writes it, with the equals sign dropped."""
    if BOUND_RE.search(spec) is None:
        return None

    return spec.replace("==", "").strip()


def read_installs(sources: list[str]) -> dict:
    pinned: dict[str, str] = {}
    unpinned: set[str] = set()

    for source in sources:
        for line in source.splitlines():
            if line.lstrip().startswith("#"):
                continue

            for package, spec in requirements(line):
                if not spec:
                    unpinned.add(package)
                    continue

                bound = clean_spec(spec)

                if bound is None:
                    unpinned.add(package)
                else:
                    pinned[package] = bound
                    unpinned.discard(package)

    return {"pinned": pinned, "unpinned": sorted(unpinned - set(pinned))}


def without_comments(source: str) -> str:
    return "\n".join(line.split("#")[0] for line in source.splitlines())


def read_patterns(sources: list[str]) -> list[dict]:
    """Which recorded API calls the code makes. Comments are not code: one C8
    notebook names openai.ChatCompletion only to say it has been replaced. A
    removed call must match as a whole name, or LLMChainExtractor, a different
    class, reads as LLMChain."""
    code = "\n".join(without_comments(source) for source in sources)
    found = []

    for package, markers in PATTERNS.items():
        for needle, name, note in markers:
            legacy = note != "current"
            pattern = rf"(?<![\w.]){re.escape(needle)}" + (r"(?!\w)" if legacy else "")

            if re.search(pattern, code):
                found.append({"package": package, "uses": name, "note": note, "legacy": legacy})

    return found


def scan(notebook: dict) -> dict:
    sources = code_cells(notebook)
    installs = read_installs(sources)

    return {
        "pinned": installs["pinned"],
        "unpinned": installs["unpinned"],
        "patterns": read_patterns(sources),
    }


def scan_file(path: Path) -> dict:
    report = scan(json.loads(path.read_text(encoding="utf-8")))
    report["file"] = path.name
    report["week"] = path.parent.name
    return report


def scan_all(root: Path) -> list[dict]:
    files = sorted(root.rglob("*.ipynb")) if root.is_dir() else [root]

    if not files:
        raise SystemExit(f"no notebooks under {root}")

    return [scan_file(path) for path in files]


def fingerprint(notebook: dict) -> str:
    """Every cell's type and source, in order, hashed. Two notebooks with the same
    fingerprint teach the same thing cell for cell, whatever their file names say."""
    parts = []

    for cell in notebook.get("cells", []):
        source = cell.get("source", "")
        parts.append(cell.get("cell_type", "") + "\x00" + ("".join(source) if isinstance(source, list) else source))

    return hashlib.sha256("\x01".join(parts).encode("utf-8")).hexdigest()


def copies(files: list[Path]) -> list[dict]:
    """Notebooks that are another notebook under a second name. The one kept is the
    name a download did not number: "x.ipynb" over "x (1).ipynb", then the shorter."""
    groups = defaultdict(list)

    for path in files:
        notebook = json.loads(path.read_text(encoding="utf-8"))
        groups[fingerprint(notebook)].append((path, len(notebook.get("cells", []))))

    found = []

    for members in groups.values():
        if len(members) < 2:
            continue

        members.sort(key=lambda member: (bool(COPY_SUFFIX_RE.search(member[0].stem)), len(member[0].name), member[0].name))
        kept = members[0][0]

        for path, cells in members[1:]:
            found.append({"notebook": path.as_posix(), "same_as": kept.as_posix(), "cells": cells})

    return sorted(found, key=lambda copy: copy["notebook"])


def summarise(reports: list[dict]) -> dict:
    by_week = defaultdict(lambda: {"pinned": defaultdict(set), "unpinned": defaultdict(int), "legacy": defaultdict(int)})

    for report in reports:
        week = by_week[report["week"]]

        for package, version in report["pinned"].items():
            week["pinned"][package].add(version)

        for package in report["unpinned"]:
            week["unpinned"][package] += 1

        for pattern in report["patterns"]:
            if pattern["legacy"]:
                week["legacy"][pattern["uses"]] += 1

    return by_week


def main() -> None:
    parser = argparse.ArgumentParser(description="Read course notebooks and report what they install and use.")
    parser.add_argument("path", nargs="?", default=str(NOTEBOOK_DIR))
    parser.add_argument("--by-week", action="store_true")
    args = parser.parse_args()

    reports = scan_all(Path(args.path))

    if args.by_week:
        for week, data in sorted(summarise(reports).items()):
            print(f"\n{week}")
            for package, versions in sorted(data["pinned"].items()):
                print(f"  runs      {package} {', '.join(sorted(versions))}")
            for package, count in sorted(data["unpinned"].items(), key=lambda i: -i[1])[:8]:
                print(f"  unpinned  {package} ({count} notebooks)")
            for name, count in sorted(data["legacy"].items(), key=lambda i: -i[1]):
                print(f"  legacy    {name} ({count} notebooks)")
        return

    for report in reports:
        print(f"\n{report['week']} / {report['file']}")
        for package, version in sorted(report["pinned"].items()):
            print(f"  runs      {package} {version}")
        if report["unpinned"]:
            print(f"  unpinned  {', '.join(report['unpinned'])}")
        for pattern in report["patterns"]:
            if pattern["legacy"]:
                print(f"  legacy    {pattern['uses']} ({pattern['note']})")


if __name__ == "__main__":
    main()
