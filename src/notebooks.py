import argparse
import json
import re
from pathlib import Path

NOTEBOOK_DIR = Path("notebooks")

INSTALL_RE = re.compile(r"([A-Za-z0-9_.\-\[\]]+)\s*==\s*([0-9][A-Za-z0-9.\-]*)")
PIP_LINE_RE = re.compile(r"^\s*[!%]?\s*(?:pip|pip3|uv pip|python -m pip)\s+install\b(.*)$", re.MULTILINE)

PATTERNS = {
    "langchain": [
        ("RetrievalQA", "RetrievalQA chain", "replaced by LCEL and create_retrieval_chain in 0.2+"),
        ("load_qa_chain", "load_qa_chain", "removed from langchain 1.x"),
        ("initialize_agent", "initialize_agent", "replaced by the agent constructors in langgraph"),
        ("LLMChain", "LLMChain", "replaced by the pipe operator in LCEL"),
        ("ConversationBufferMemory", "ConversationBufferMemory", "replaced by message history objects"),
        ("create_retrieval_chain", "create_retrieval_chain", "current"),
        ("|", "LCEL pipes", "current"),
    ],
    "openai": [
        ("openai.ChatCompletion", "openai.ChatCompletion", "removed in openai 1.x"),
        ("openai.Completion", "openai.Completion", "removed in openai 1.x"),
        ("OpenAI(", "the OpenAI client", "current"),
        ("client.chat.completions", "client.chat.completions", "current"),
    ],
    "transformers": [
        ("pipeline(", "the pipeline helper", "current"),
        ("Trainer(", "Trainer", "current"),
        ("AutoModelFor", "Auto classes", "current"),
    ],
    "langgraph": [
        ("StateGraph", "StateGraph", "current"),
        ("MessageGraph", "MessageGraph", "removed in langgraph 0.3+"),
        ("create_react_agent", "create_react_agent", "current"),
    ],
}


def cells(notebook: dict) -> list[str]:
    sources = []

    for cell in notebook.get("cells", []):
        source = cell.get("source", "")
        sources.append("".join(source) if isinstance(source, list) else source)

    return sources


def find_pins(code: str) -> dict[str, str]:
    pins = {}

    for arguments in PIP_LINE_RE.findall(code):
        for package, version in INSTALL_RE.findall(arguments):
            pins[package.split("[")[0].lower()] = version

    return pins


def find_patterns(code: str) -> list[dict]:
    found = []

    for package, markers in PATTERNS.items():
        for needle, name, note in markers:
            if needle == "|":
                continue
            if needle in code:
                found.append({"package": package, "uses": name, "note": note})

    return found


def scan(notebook: dict) -> dict:
    code = "\n".join(cells(notebook))

    return {"pins": find_pins(code), "patterns": find_patterns(code)}


def scan_file(path: Path) -> dict:
    result = scan(json.loads(path.read_text(encoding="utf-8")))
    result["file"] = path.name
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Read course notebooks and report what they install and use.")
    parser.add_argument("path", nargs="?", default=str(NOTEBOOK_DIR))
    args = parser.parse_args()

    root = Path(args.path)
    files = sorted(root.rglob("*.ipynb")) if root.is_dir() else [root]

    if not files:
        raise SystemExit(f"no notebooks under {root}")

    for path in files:
        report = scan_file(path)
        print(f"\n{report['file']}")

        if report["pins"]:
            for package, version in sorted(report["pins"].items()):
                print(f"  installs  {package} {version}")
        else:
            print("  installs  nothing pinned")

        for pattern in report["patterns"]:
            print(f"  uses      {pattern['uses']} ({pattern['note']})")


if __name__ == "__main__":
    main()
