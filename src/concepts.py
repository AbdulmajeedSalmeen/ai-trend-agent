"""What the tools the course teaches now offer that the course's own version did not.

For each tool, the module list of the version the notebooks pin is compared with
the module list of the newest release, both read at their release tags on
GitHub. A module the newest release added is a candidate concept. What it is
comes from its own docstring, read from the release, never from the model.

Demand is measured only where it can be: a name distinct enough to search, such
as MCP, is counted in the same "Who is hiring?" threads the run reads. A common
word such as "messages" would match every post, so it is left unmeasured rather
than counted. Whether the course already covers it is read from the notebooks.
"""

import ast
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from src import arabic
from src.notebooks import code_cells, read_installs
from src.sources import market

API = "https://api.github.com/repos/{repo}/contents/{path}"
RAW = "https://raw.githubusercontent.com/{repo}/{tag}/{path}"
PAGE = "https://github.com/{repo}/tree/{tag}/{path}"
PYPI = "https://pypi.org/pypi/{name}/json"

# Where each tool's package sits in its repository, by major version, and how its
# release tags are named. langchain moved its package when 1.0 shipped; the
# langchain_v1 folder at a 0.x tag is unreleased work, not what 0.x installed.
TOOLS = {
    "langchain": ("langchain-ai/langchain", {0: "libs/langchain/langchain", 1: "libs/langchain_v1/langchain"},
                  "langchain=={version}"),
    "langgraph": ("langchain-ai/langgraph", {0: "libs/langgraph/langgraph", 1: "libs/langgraph/langgraph"},
                  "{version}"),
}

ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")
# Where a concept is too new for the curriculum to have it, a lesson needs
# employers asking: 5 posts in three months is where the market scale reaches 3.
LESSON_JOBS = 5
NOTEBOOK_TOTAL_KEY = "notebooks_read"


def get_json(url: str, **params) -> dict | list:
    response = requests.get(url, params=params, timeout=20,
                            headers={"Accept": "application/vnd.github+json", "User-Agent": "ai-trend-agent"})
    response.raise_for_status()
    return response.json()


def get_text(url: str) -> str | None:
    response = requests.get(url, timeout=20, headers={"User-Agent": "ai-trend-agent"})

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.text


def stable(releases: list[str]) -> list[Version]:
    found = []

    for release in releases:
        try:
            version = Version(release)
        except InvalidVersion:
            continue

        if not version.is_prerelease:
            found.append(version)

    return found


def course_version(package: str, notebooks: list[dict], releases: list[str]) -> str | None:
    """The release the notebooks that pin the tool would install: the newest one
    their most common bound allows. Unbound installs say nothing about which
    version the material was written against, so they are left out."""
    specs = Counter(installs["pinned"][package] for installs in notebooks if package in installs["pinned"])

    if not specs:
        return None

    spec = specs.most_common(1)[0][0]

    try:
        bound = SpecifierSet(spec if spec[0] in "<>=!~" else f"=={spec}")
    except InvalidSpecifier:
        return None

    allowed = [version for version in stable(releases) if bound.contains(version)]

    return str(max(allowed)) if allowed else None


def modules(repo: str, root: str, tag: str, fetch_json=get_json) -> dict[str, str]:
    """Public modules at a tag: name to "dir" or "file"."""
    found = {}

    for entry in fetch_json(API.format(repo=repo, path=root), ref=tag):
        name = entry["name"]

        if name.startswith(("_", ".")):
            continue

        if entry["type"] == "dir":
            found[name] = "dir"
        elif name.endswith(".py"):
            found[name[:-3]] = "file"

    return found


def first_sentence(source: str | None) -> str | None:
    if not source:
        return None

    try:
        text = ast.get_docstring(ast.parse(source)) or ""
    except SyntaxError:
        return None

    paragraph = text.strip().split("\n\n")[0].replace("\n", " ").strip()
    return paragraph or None


def search_term(module: str, summary: str | None) -> str | None:
    """The name to count in job posts: an acronym the module's own docstring uses
    for itself, such as MCP for langchain.mcp. None for a common word."""
    for acronym in ACRONYM_RE.findall(summary or ""):
        if acronym.lower() == module.lower():
            return acronym

    return None


def mentions(texts: list[str], dotted: str, term: str | None) -> int:
    """How many notebooks name the module, or the concept's own term, anywhere."""
    patterns = [re.compile(rf"(?<![\w.]){re.escape(dotted)}(?![\w])")]

    if term:
        patterns.append(re.compile(rf"\b{re.escape(term)}\b"))

    return sum(1 for text in texts if any(pattern.search(text) for pattern in patterns))


def notebook_text(notebook: dict) -> str:
    """Code and prose alike: a concept counts as taught if a notebook explains it."""
    parts = []

    for cell in notebook.get("cells", []):
        source = cell.get("source", "")
        parts.append("".join(source) if isinstance(source, list) else source)

    return "\n".join(parts)


def decide(concept: dict) -> str:
    if concept["notebooks"]:
        return "watch"

    jobs = concept["jobs"]

    if jobs is None or jobs == 0:
        return "watch"

    return "add_new_lesson" if jobs >= LESSON_JOBS else "add_optional_content"


def find(files: list[Path], fetch_json=get_json, fetch_text=get_text, count_jobs=None,
         releases_of=None, months: int = 3) -> dict:
    """Candidate concepts from every tool in TOOLS, with the facts to judge them."""
    notebooks = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    texts = [notebook_text(notebook) for notebook in notebooks]
    installs = [read_installs(code_cells(notebook)) for notebook in notebooks]
    releases_of = releases_of or (lambda name: list(get_json(PYPI.format(name=name))["releases"]))

    if count_jobs is None:
        threads = [thread["id"] for thread in market.hiring_threads(months)]
        count_jobs = lambda term: market.job_posts(term, threads)

    found, checked = [], {}

    for tool, (repo, roots, tag_format) in TOOLS.items():
        releases = releases_of(tool)
        newest = max(stable(releases), default=None)
        taught = course_version(tool, installs, releases)

        if newest is None or taught is None:
            continue

        latest, old = str(newest), taught
        new_tag, old_tag = tag_format.format(version=latest), tag_format.format(version=old)
        new_root = roots.get(newest.major, roots[max(roots)])
        old_root = roots.get(Version(old).major, roots[max(roots)])
        checked[tool] = {"course": old, "latest": latest}
        now = modules(repo, new_root, new_tag, fetch_json)
        added = sorted(set(now) - set(modules(repo, old_root, old_tag, fetch_json)))

        for name in added:
            relative = f"{name}/__init__.py" if now[name] == "dir" else f"{name}.py"
            summary = first_sentence(fetch_text(RAW.format(repo=repo, tag=quote(new_tag, safe=""),
                                                           path=f"{new_root}/{relative}")))

            # A module that does not say what it is cannot be taught from here.
            if summary is None:
                continue

            term = search_term(name, summary)
            dotted = f"{tool}.{name}"
            concept = {
                "concept": term or dotted,
                "module": dotted,
                "tool": tool,
                "summary": summary,
                "latest": latest,
                "course_version": old,
                "term": term,
                "jobs": count_jobs(term) if term else None,
                "months": months,
                "notebooks": mentions(texts, dotted, term),
                NOTEBOOK_TOTAL_KEY: len(texts),
                "evidence": [
                    {"what": "added", "release": f"{tool} {latest}",
                     "url": PAGE.format(repo=repo, tag=quote(new_tag, safe=""), path=f"{new_root}/{name}")},
                    {"what": "absent", "release": f"{tool} {old}",
                     "url": PAGE.format(repo=repo, tag=quote(old_tag, safe=""), path=old_root)},
                ],
                "suggested_chapter": None,
            }
            concept["action"] = decide(concept)
            found.append(concept)

    order = {"add_new_lesson": 0, "add_optional_content": 1, "watch": 2}
    found.sort(key=lambda concept: (order[concept["action"]], -(concept["jobs"] or 0), concept["module"]))

    return {"concepts": found, "checked": {**checked, "on": date.today().isoformat()}}


def why(concept: dict) -> tuple[str, str]:
    """The reason in English and Arabic, from the facts alone."""
    tool, module = concept["tool"], concept["module"]
    latest, old = f"{tool} {concept['latest']}", f"{tool} {concept['course_version']}"
    total, used = concept[NOTEBOOK_TOTAL_KEY], concept["notebooks"]
    term, jobs, months = concept["term"], concept["jobs"], concept["months"]

    english = [f"{latest} added {module}, which {old}, the newest version the course's pins allow, does not have."]
    arabic_parts = [f"أضافت {latest} الوحدة {module}، وليست في {old}، أحدث نسخة تسمح بها تثبيتات المقرر."]

    if jobs is None:
        english.append("Not counted in job posts: the name is too common to search.")
        arabic_parts.append("لم يُحصَ في الوظائف: الاسم أعمّ من أن يُبحث عنه.")
    elif jobs == 0:
        english.append(f"No job post named {term} in the last {months} months.")
        arabic_parts.append(f"لم تذكر أي وظيفة {term} في آخر {arabic.counted(months, arabic.MONTH)}.")
    else:
        english.append(f"{jobs} job post{'s' if jobs != 1 else ''} named {term} in the last {months} months.")
        verb = "ذكرتا" if jobs == 2 else "ذكرت"
        arabic_parts.append(f"{arabic.counted(jobs, arabic.JOB)} {verb} {term} في آخر "
                            f"{arabic.counted(months, arabic.MONTH)}.")

    if used == 0:
        english.append(f"None of the {total} notebooks mentions it.")
        arabic_parts.append(f"لا يذكره أي نوتبوك من {total}.")
    else:
        english.append(f"{used} of the {total} notebooks mention{'s' if used == 1 else ''} it already.")
        arabic_parts.append(f"يذكره {arabic.counted(used, arabic.NOTEBOOK)} من {total} بالفعل.")

    return " ".join(english), " ".join(arabic_parts)
