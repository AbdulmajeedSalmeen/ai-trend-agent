"""What to change in the course material itself, not only which package moved.

Every `from langchain... import ...` line in the notebooks is checked against the
source of the release a student installs today, read at its tag on GitHub: does
the module still exist, and does it still export the name? When it does not, the
same check looks for the name in the packages LangChain moved code into, so the
proposed line is read from a release too, never recalled.

Only the `langchain` package is checked. It is the one that shipped a major
release the course has not followed. The packages it moved code into are read
only to find where a name went.
"""

import ast
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from src import arabic
from src.notebooks import read_installs

RAW = "https://raw.githubusercontent.com/{repo}/{tag}/{path}"
PAGE = "https://github.com/{repo}/{kind}/{tag}/{path}"
PYPI = "https://pypi.org/pypi/{name}/json"

CHECKED = "langchain"

# Where each package's code sits in its repository, and how its release tags are
# named. This says where to read, never what is there.
SOURCES = {
    "langchain": ("langchain-ai/langchain", "libs/langchain_v1/langchain", "langchain"),
    "langchain_core": ("langchain-ai/langchain", "libs/core/langchain_core", "langchain-core"),
    "langchain_openai": ("langchain-ai/langchain", "libs/partners/openai/langchain_openai", "langchain-openai"),
    "langchain_classic": ("langchain-ai/langchain", "libs/langchain/langchain_classic", "langchain-classic"),
}

# Where a name that left langchain can have gone, in the order to look. Core and
# classic keep the module path (langchain.agents becomes langchain_classic.agents);
# a partner package exports its classes from the top. The partner comes before
# classic because classic keeps some old paths alive only as shims.
SUCCESSORS = [("langchain_core", True), ("langchain_openai", False), ("langchain_classic", True)]

IMPORT_RE = re.compile(r"^(\s*)from\s+(langchain(?:\.[\w.]+)?)\s+import\s+(.+)$")


def fetch_text(url: str) -> str | None:
    response = requests.get(url, timeout=20, headers={"User-Agent": "ai-trend-agent"})

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.text


def latest_version(distribution: str) -> str:
    response = requests.get(PYPI.format(name=distribution), timeout=20)
    response.raise_for_status()
    return response.json()["info"]["version"]


def exported(source: str) -> set[str]:
    """Names a module offers: its __all__, and whatever it defines or imports at
    the top level. The union, so a name is never called gone for being unlisted.

    A module with a top-level __getattr__ loads its names on first use, from a
    dict of name to module path (langchain_classic.chains does this for
    RetrievalQA), so the string keys of its dicts count as offered too."""
    names: set[str] = set()
    tree = ast.parse(source)
    lazy = any(isinstance(node, ast.FunctionDef) and node.name == "__getattr__" for node in tree.body)

    for node in tree.body:
        if lazy and isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict):
            names |= {key.value for key in node.value.keys
                      if isinstance(key, ast.Constant) and isinstance(key.value, str)}

        targets = []

        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]

        for target in targets:
            if not isinstance(target, ast.Name):
                continue

            names.add(target.id)

            if target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                names |= {item.value for item in node.value.elts
                          if isinstance(item, ast.Constant) and isinstance(item.value, str)}

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(alias.asname or alias.name).split(".")[0] for alias in node.names}

    return names


class Release:
    """One package at one version, read file by file from its release tag."""

    def __init__(self, package: str, version: str, fetch=fetch_text):
        self.package, self.version, self.fetch = package, version, fetch
        self.repo, self.root, self.distribution = SOURCES[package]
        self.tag = f"{self.distribution}=={version}"
        self.files: dict[str, str | None] = {}

    def __str__(self) -> str:
        return f"{self.distribution} {self.version}"

    def read(self, relative: str) -> str | None:
        if relative not in self.files:
            url = RAW.format(repo=self.repo, tag=quote(self.tag, safe=""), path=f"{self.root}/{relative}")
            self.files[relative] = self.fetch(url)

        return self.files[relative]

    def module_file(self, sub: str) -> str | None:
        """The file that defines a module, or None when this release has no such module."""
        base = sub.replace(".", "/")

        for relative in ([f"{base}/__init__.py", f"{base}.py"] if base else ["__init__.py"]):
            if self.read(relative) is not None:
                return relative

        return None

    def has(self, sub: str, name: str) -> bool:
        relative = self.module_file(sub)

        if relative is None:
            return False

        if name in exported(self.read(relative)):
            return True

        # A submodule can be imported by name whether or not its parent lists it.
        return self.module_file(f"{sub}.{name}" if sub else name) is not None

    def page(self, relative: str | None = None) -> str:
        """The page a reader can open to see the file, or the package folder, at this tag."""
        path = f"{self.root}/{relative}" if relative else self.root
        return PAGE.format(repo=self.repo, kind="blob" if relative else "tree", tag=quote(self.tag, safe=""), path=path)


def cells(notebook: dict) -> list[tuple[int, str]]:
    """(position, source) for each code cell. Positions count every cell from the
    top, starting at 1, the way a teacher scrolling the notebook would count."""
    found = []

    for position, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", "")
        found.append((position, "".join(source) if isinstance(source, list) else source))

    return found


def import_statements(source: str) -> list[dict]:
    """Every `from langchain... import ...` in a cell, with a parenthesised list
    joined into one statement and the original text kept for the edit."""
    lines = source.splitlines()
    found = []
    index = 0

    while index < len(lines):
        match = IMPORT_RE.match(lines[index])

        if match is None:
            index += 1
            continue

        text = [lines[index]]
        tail = match.group(3)

        if "(" in tail and ")" not in tail:
            while index + 1 < len(lines) and ")" not in lines[index]:
                index += 1
                text.append(lines[index])
            tail = " ".join(part.strip() for part in [tail] + text[1:])

        names = []

        for part in tail.split("#")[0].replace("(", " ").replace(")", " ").replace("\\", " ").split(","):
            part = part.strip()

            if part:
                name, _, alias = part.partition(" as ")
                names.append((name.strip(), alias.strip() or None))

        found.append({"indent": match.group(1), "module": match.group(2), "names": names,
                      "current": "\n".join(text)})
        index += 1

    return found


def spelled(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def import_line(indent: str, module: str, names: list[tuple[str, str | None]]) -> str:
    listed = ", ".join(f"{name} as {alias}" if alias else name for name, alias in names)
    return f"{indent}from {module} import {listed}"


def check_import(statement: dict, releases: dict) -> dict | None:
    """The edit one import needs, or None when the release still has every name."""
    checked = releases[CHECKED]
    sub = statement["module"].partition(".")[2]
    module_exists = checked.module_file(sub) is not None
    staying, moving = [], {}

    for name, alias in statement["names"]:
        if module_exists and checked.has(sub, name):
            staying.append((name, alias))
            continue

        target = None

        for package, keep_path in SUCCESSORS:
            path = sub if keep_path else ""

            if releases[package].has(path, name):
                target = (package + (f".{path}" if path else ""), package)
                break

        moving.setdefault(target, []).append((name, alias))

    if not moving:
        return None

    proposed = [import_line(statement["indent"], statement["module"], staying)] if staying else []
    reasons, reasons_ar, moved_to = [], [], []

    for target, names in moving.items():
        plain = [name for name, _ in names]

        if target is None:
            proposed.append(f"{statement['indent']}# {', '.join(plain)}: not found in any release we read")
            reasons.append(f"{spelled(plain)} {'are' if len(plain) > 1 else 'is'} in none of the releases "
                           f"we read, so this line needs rewriting.")
            reasons_ar.append(f"{arabic.listed(plain)} غير موجودة في أي إصدار قرأناه، فهذا السطر يحتاج إعادة كتابة.")
            continue

        module, package = target
        release = releases[package]
        path = module.partition(".")[2]
        child = f"{path}.{plain[0]}" if path else plain[0]
        proposed.append(import_line(statement["indent"], module, names))
        moved_to.append({"module": module, "release": str(release),
                         "url": release.page(release.module_file(child) or release.module_file(path))})
        now = "They now come" if len(plain) > 1 else "It now comes"

        if not sub:
            reasons.append(f"{checked} no longer has {spelled(plain)}. {now} from {module} in {release}.")
            reasons_ar.append(f"لم يعد {checked} يضم {arabic.listed(plain)}، وهي الآن من {module} في {release}.")
        elif module_exists:
            reasons.append(f"{statement['module']} in {checked} no longer has {spelled(plain)}. "
                           f"{now} from {module} in {release}.")
            reasons_ar.append(f"لم تعد {statement['module']} في {checked} تضم {arabic.listed(plain)}، "
                              f"وهي الآن من {module} في {release}.")
        else:
            reasons.append(f"{checked} has no {statement['module']} module. {now} from {module} in {release}.")
            reasons_ar.append(f"لا توجد وحدة {statement['module']} في {checked}، "
                              f"و{arabic.listed(plain)} الآن من {module} في {release}.")

    return {
        "kind": "replace",
        "current": statement["current"],
        "proposed": "\n".join(proposed),
        "names": [name for names in moving.values() for name, _ in names],
        "reason": " ".join(reasons),
        "reason_ar": " ".join(reasons_ar),
        "checked": str(checked),
        "evidence_url": checked.page(checked.module_file(sub)) if module_exists else checked.page(),
        "moved_to": moved_to,
    }


def keeps_old_line(spec: str | None, version: str) -> bool | None:
    """Whether a notebook's own pin keeps it off the version checked: True when
    it runs as pinned, False when a fresh install gets the new release, None
    when the notebook does not install the package at all."""
    if spec is None:
        return None

    if spec == "unpinned":
        return False

    try:
        bound = SpecifierSet(spec if spec[0] in "<>=!~" else f"=={spec}")
    except InvalidSpecifier:
        return False

    return version not in bound


def install_edit(sources: list[tuple[int, str]], release: Release) -> dict | None:
    """Add a package the proposed imports need to the notebook's own install line."""
    needed = release.distribution

    for position, source in sources:
        for line in source.splitlines():
            if re.search(r"\bpip\b.*\binstall\b.*\blangchain\b", line) and needed not in line:
                return {"cell": position, "kind": "replace", "current": line.rstrip(),
                        "proposed": f"{line.rstrip()} {needed}", "names": [needed],
                        "reason": f"The imports below need {needed}, which this notebook does not install.",
                        "reason_ar": f"الاستيرادات أدناه تحتاج {needed}، وهذا النوتبوك لا يثبّتها.",
                        "checked": str(release), "evidence_url": f"https://pypi.org/project/{needed}/{release.version}/",
                        "moved_to": []}
    return None


def check_notebook(path: Path, notebook: dict, releases: dict) -> list[dict]:
    sources = cells(notebook)
    installs = read_installs([source for _, source in sources])
    spec = installs["pinned"].get(CHECKED) or ("unpinned" if CHECKED in installs["unpinned"] else None)
    runs_as_pinned = keeps_old_line(spec, releases[CHECKED].version)
    edits = []

    for position, source in sources:
        for statement in import_statements(source):
            edit = check_import(statement, releases)

            if edit:
                edits.append({"cell": position, **edit})

    classic = releases["langchain_classic"]
    wanted = any(moved["release"] == str(classic) for edit in edits for moved in edit["moved_to"])
    installed = installs["unpinned"] + list(installs["pinned"])

    # Only a notebook that would get the new release today needs the package now.
    # One that runs as pinned needs it only when the course moves, with the rest
    # of its pins.
    if wanted and runs_as_pinned is False and classic.distribution not in installed:
        extra = install_edit(sources, classic)

        if extra:
            edits.insert(0, extra)

    notebook_path = path.as_posix()

    return [{"notebook": notebook_path, "package": CHECKED, "installs": spec,
             "runs_as_pinned": runs_as_pinned, **edit} for edit in edits]


def releases_now(fetch=fetch_text, version_of=latest_version) -> dict:
    return {package: Release(package, version_of(distribution), fetch)
            for package, (_, _, distribution) in SOURCES.items()}


def check_all(files: list[Path], chapter_of, releases: dict) -> dict:
    """Edits per chapter, and what was read to decide them."""
    by_chapter: dict[str, list[dict]] = {}

    for path in files:
        chapter_id = chapter_of(path)

        if chapter_id is None:
            continue

        notebook = json.loads(path.read_text(encoding="utf-8"))

        for edit in check_notebook(path, notebook, releases):
            by_chapter.setdefault(chapter_id, []).append({"chapter_id": chapter_id, **edit})

    checked = {release.distribution: release.version for release in releases.values()}

    return {"edits": by_chapter, "checked": {**checked, "on": date.today().isoformat()}}
