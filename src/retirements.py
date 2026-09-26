"""Which course notebooks call a model OpenAI has scheduled to shut down.

The dates are OpenAI's own, copied row by row from its deprecations page into
fixtures/model_retirements.json with the day they were read. Which notebooks a
date reaches is measured here, from the code cells: a model id written whole in
quotes, or a LangChain constructor called with no model, whose default was read
from the release source. A reviewer can say a notebook is affected; only this
says how many, and a count on the page is never typed.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from src import arabic
from src.notebooks import without_comments

RETIREMENTS_PATH = Path("fixtures/model_retirements.json")

# A model id the way code passes one: whole, inside quotes. Prose that mentions
# "GPT-5" is not a call, and neither is an id inside a longer string.
MODEL_ID_RE = re.compile(
    r"""["']((?:gpt|chatgpt)-[A-Za-z0-9.\-:]+|o[1-9](?:-[A-Za-z0-9.\-]+)?|(?:text-)?(?:davinci|babbage)-[A-Za-z0-9.\-]+)["']""")

# What a notebook imports from LangChain. The SDK's own `openai.OpenAI()` is a
# client with no default model: every request names its model, so it never counts.
LANGCHAIN_IMPORT_RE = re.compile(r"^\s*from\s+(langchain[\w.]*)\s+import\s+(\([^)]*\)|[^\n]+)", re.M)
SDK_IMPORT_RE = re.compile(r"^\s*from\s+openai\s+import\s+(\([^)]*\)|[^\n]+)", re.M)


def load(path: Path = RETIREMENTS_PATH) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def arguments(source: str, name: str) -> list[str]:
    """The argument text of every `name(...)` call, with nested brackets kept whole,
    so `OpenAI(temperature=float(x))` is read as one call and not cut short."""
    found = []

    for match in re.finditer(rf"(?<![\w.]){re.escape(name)}\s*\(", source):
        depth, end = 1, match.end()

        while end < len(source) and depth:
            depth += {"(": 1, ")": -1}.get(source[end], 0)
            end += 1

        found.append(source[match.end():end - 1])

    return found


def imported(pattern: re.Pattern, code: str, name: str) -> bool:
    return any(re.search(rf"\b{name}\b", match.group(match.lastindex)) for match in pattern.finditer(code))


def calls(notebook: dict, defaults: dict) -> list[dict]:
    """Every model a notebook's code reaches, with the cell it is in. Cells are
    counted from 1 across every cell, the way the import check counts them."""
    cells = []

    for position, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", "")
        cells.append((position, without_comments("".join(source) if isinstance(source, list) else source)))

    code = "\n".join(source for _, source in cells)
    found = []

    for position, source in cells:
        for match in MODEL_ID_RE.finditer(source):
            found.append({"model": match.group(1), "cell": position, "how": "named"})

    for constructor, default in defaults.items():
        # A class imported from both the SDK and LangChain in one notebook cannot
        # be told apart by name, so neither import is guessed at.
        if not imported(LANGCHAIN_IMPORT_RE, code, constructor) or imported(SDK_IMPORT_RE, code, constructor):
            continue

        for position, source in cells:
            if any("model" not in args for args in arguments(source, constructor)):
                found.append({"model": default["model"], "cell": position, "how": "default",
                              "constructor": constructor})

    return found


def scan(files: list[Path], data: dict | None) -> list[dict]:
    """The notebooks that reach any model, each with what it reaches and where."""
    if data is None:
        return []

    found = []

    for path in files:
        notebook = json.loads(path.read_text(encoding="utf-8"))
        reached = calls(notebook, data.get("defaults", {}))

        if reached:
            found.append({"notebook": path.as_posix(), "calls": reached})

    return found


def deadlines(model_calls: list[dict], data: dict | None, left_out: set[str] = frozenset()) -> list[dict]:
    """One entry per shutdown date that reaches at least one notebook, soonest first.
    `left_out` holds notebooks that are copies of another, so each is counted once."""
    if not data:
        return []

    rows = {model_id: row for row in data["retirements"] for model_id in row["ids"]}
    dates: dict[str, dict] = defaultdict(lambda: {"named": defaultdict(set), "default": defaultdict(set),
                                                  "replacements": set(), "announced": set()})

    for entry in model_calls:
        if entry["notebook"] in left_out:
            continue

        for call in entry["calls"]:
            row = rows.get(call["model"])

            if row is None:
                continue

            date = dates[row["shutdown"]]
            date["announced"].add(row["announced"])
            date["replacements"].add(row["replacement"])

            if call["how"] == "named":
                date["named"][call["model"]].add(entry["notebook"])
            else:
                date["default"][(call["constructor"], call["model"])].add(entry["notebook"])

    found = []

    for shutdown in sorted(dates):
        date = dates[shutdown]
        named = set().union(*date["named"].values()) if date["named"] else set()
        by_default = set().union(*date["default"].values()) if date["default"] else set()
        models = sorted(set(date["named"]) | {model for _, model in date["default"]})
        constructors = sorted({constructor for constructor, _ in date["default"]})
        english, arabic_text = explain(shutdown, date, named, by_default)
        found.append({
            "date": shutdown,
            "announced": sorted(date["announced"]),
            "what": ", ".join(models),
            "books": len(named | by_default),
            "named": len(named),
            "by_default": len(by_default),
            "constructors": constructors,
            "replacement": ", ".join(sorted(date["replacements"])),
            "notebooks": sorted(named | by_default),
            "why": english,
            "why_ar": arabic_text,
        })

    return found


def explain(shutdown: str, date: dict, named: set, by_default: set) -> tuple[str, str]:
    parts, parts_ar = [], []

    if named:
        models = sorted(date["named"])
        noun = "notebook names" if len(named) == 1 else "notebooks name"
        parts.append(f"{len(named)} {noun} {' or '.join(models)} in a code cell")
        parts_ar.append(arabic.named_models(len(named), models))

    for (constructor, model), notebooks in sorted(date["default"].items()):
        noun = "notebook calls" if len(notebooks) == 1 else "notebooks call"
        parts.append(f"{len(notebooks)} {noun} LangChain's {constructor}() with no model, "
                     f"which defaults to {model}")
        parts_ar.append(arabic.default_model(len(notebooks), constructor, model))

    reached = set(date["named"]) | {model for _, model in date["default"]}
    english = "; ".join(parts) + f". OpenAI shuts {'it' if len(reached) == 1 else 'them'} down on {shutdown}."
    return english, arabic.shutdown_sentence(parts_ar, shutdown)
