"""A second source for a claim only one document supports.

Most of what this run confirms, it confirms with the very document the claim was read
from: 137 of 168 claims on the last run, each worth 0.7 because a release page saying
what the release page said is not a check. Twenty-seven did better, because we happened
to hold both the registry record and the repository's release. The difference is not
that those releases are better attested. It is that we collected two documents for them
and one for the rest.

So the question is never "is there a second source", it is "where would it be", and
that changes per package. A package published to PyPI from a repository we do not
follow has its second source in that repository's releases. One whose repository cuts
no releases has it in a changelog file. One that is a folder inside a monorepo has it
under a tag nobody would guess from the package name. A fixed order of places to look
answers none of that, which is why this is a loop: it decides where to look next, looks,
and either finds the version written somewhere else or says it could not.

Two rules stand under it:

  1. The line it quotes must be in what a tool returned this run, and that line must
     contain the version. A second source that does not name the version is not a
     second source for this claim.
  2. The link it gives must be one a tool printed. It may not compose a plausible URL.

What survives raises the claim from a document repeating itself to two records
agreeing, which is what the rules have always called a registry match, and the claim
records that this one was searched for rather than collected.
"""

import json
import re

import requests
from packaging.version import InvalidVersion, Version

from src import trace
from src.adapters import model
from src.agents import citations
from src.schema import Claim

MAX_STEPS = 4
MAX_TOOL_CHARS = 1800
# What a second record has to be. We hold the registry's word, so the repository is the
# other party; we hold the repository's, so the registry is. Another page of the record
# we already have is the same publisher saying the same thing in the same place.
OTHER_PARTY = {"pypi": "github.com", "github": "pypi.org"}
# The tools that read the other party's record. We hold the registry's word for a claim
# PyPI gave us, so only the repository can second it, and the other way round.
OTHER_TOOLS = {"pypi": {"releases", "changelog"}, "github": {"registry"}}
TIMEOUT = 20
HEADERS = {"User-Agent": "ai-trend-agent/1.0 (SDA bootcamp capstone)",
           "Accept": "application/json", "Accept-Encoding": "gzip"}
REPO_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)")

SYSTEM = (
    "You look for a second record of a software release. You are told the package, the "
    "version, and which one document we already hold. Your job is to find the version "
    "written down somewhere else: the registry, the repository's releases, or its changelog. "
    "Answer with one JSON object and nothing else, either "
    '{"tool": <name>, "args": {...}} to look, or, when you are ready, '
    '{"answer": {"found": <true|false>, "url": <a link a tool printed>, '
    '"quote": <text you are copying out of what a tool printed, containing the version>}}. '
    "The quote is a scissors job, not a sentence of your own: find the version in what a "
    'tool returned and copy that bit, for example "1.7.4 at https://pypi.org/project/x/1.7.4/". '
    "Repeating what the claim says is not a quote and is thrown away, and so is a link nobody "
    "showed you. "
    "Work out where to look. A package published from a repository has its releases there; "
    "one inside a monorepo is tagged with its own name; one that cuts no releases writes a "
    "changelog. If the version is written nowhere else you could reach, answer found false."
)

TOOL_HELP = ("registry(distribution): what the registry lists for a package, and its repository.\n"
             "releases(repo): the release tags a repository has published, newest first.\n"
             "changelog(repo): the top of the repository's changelog file.")


def flat(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def by_version(label: str):
    """Versions in version order, 1.10.0 after 1.9.0. A label that is not a version
    sorts first, so it never crowds a real release out of the newest."""
    try:
        return (1, Version(label))
    except InvalidVersion:
        return (0, Version("0"))


def named(kwargs: dict) -> str:
    """The one thing it named, whatever it called the parameter.

    A model that writes package= where the help says distribution= has still said which
    package it means. Refusing that spends a turn teaching it a keyword, and these tools
    take one argument each, so there is nothing to disambiguate.
    """
    for value in kwargs.values():
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def get_json(url: str):
    response = requests.get(url, timeout=TIMEOUT, headers=HEADERS)

    if response.status_code != 200:
        return None

    return response.json()


def get_text(url: str):
    response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": HEADERS["User-Agent"]})
    return response.text if response.status_code == 200 else None


def registry_tool(get=get_json):
    """What PyPI lists for a package, and where its source lives."""
    def registry(**kwargs) -> str:
        name = named(kwargs)

        if not name:
            return "name a package"

        try:
            payload = get(f"https://pypi.org/pypi/{name}/json")
        except requests.RequestException:
            return f"the registry could not be read for {name}"

        if not payload:
            return f"the registry lists no package called {name}"

        info = payload.get("info") or {}
        urls = " ".join(str(value) for value in (info.get("project_urls") or {}).values())
        repo = REPO_RE.search(f"{urls} {info.get('home_page') or ''}")
        versions = sorted(payload.get("releases") or {}, key=by_version)
        # Each recent version with the page that records it, so a citation can point at
        # the release rather than at the package.
        recent = "; ".join(f"{version} at https://pypi.org/project/{name}/{version}/"
                           for version in versions[-12:])
        return (f"{name} is on the registry at https://pypi.org/project/{name}/ , "
                f"source {repo.group(1) if repo else 'not stated'}, "
                f"versions listed: {', '.join(versions[-30:]) or 'none'}. "
                f"{'Each of the newest: ' + recent if recent else ''}")

    return registry


def releases_tool(get=get_json):
    """The tags a repository has actually published, which is not the same list."""
    def releases(**kwargs) -> str:
        name = named(kwargs).strip("/")

        if "/" not in name:
            return (f"{name or 'nothing'} is not a repository. This wants owner/name, like "
                    f"langchain-ai/langchain. If you do not know where the source lives, ask the "
                    f"registry for the package.")

        try:
            payload = get(f"https://api.github.com/repos/{name}/releases?per_page=100")
        except requests.RequestException:
            return f"the releases of {name} could not be read"

        if not payload:
            return f"{name} has published no releases we can read"

        lines = [f"{item.get('tag_name')} at {item.get('html_url')}" for item in payload[:60]
                 if item.get("tag_name")]
        return f"{name} releases: " + "; ".join(lines)

    return releases


def changelog_tool(get=get_text):
    """The changelog of a repository that keeps one, for a project that cuts no releases."""
    def changelog(**kwargs) -> str:
        name = named(kwargs).strip("/")

        if "/" not in name:
            return (f"{name or 'nothing'} is not a repository. This wants owner/name, like "
                    f"langchain-ai/langchain. If you do not know where the source lives, ask the "
                    f"registry for the package.")

        for branch in ("main", "master"):
            for filename in ("CHANGELOG.md", "CHANGES.md", "HISTORY.md"):
                url = f"https://raw.githubusercontent.com/{name}/{branch}/{filename}"

                try:
                    text = get(url)
                except requests.RequestException:
                    return f"the changelog of {name} could not be read"

                if text:
                    page = f"https://github.com/{name}/blob/{branch}/{filename}"
                    return f"{page} says: {text[:1400]}"

        return f"{name} keeps no changelog we can find"

    return changelog


def tools_for(json_get=get_json, text_get=get_text) -> dict:
    return {"registry": registry_tool(json_get), "releases": releases_tool(json_get),
            "changelog": changelog_tool(text_get)}


def turn(claim: Claim, came_from: str, seen: list[dict]) -> str:
    missing = {"pypi": "the repository", "github": "the registry"}.get(came_from, "everywhere else")
    lines = [f"Package: {claim.subject}", f"Version: {claim.version}",
             f"We already hold the {came_from} record of it, and nothing else, "
             f"so what we do not have is {missing}, and only a record there counts.",
             f"What it says: {claim.text}", "", "Tools:", TOOL_HELP, ""]

    if seen:
        lines.append("What you have read so far:")

        for step in seen:
            lines.append(f"- {step['tool']}({json.dumps(step['args'], ensure_ascii=False)}): {step['text']}")
    else:
        lines.append("You have read nothing yet. Decide where a second record would be.")

    lines += ["", f"You may call at most {MAX_STEPS} tools, then you must answer."]
    return "\n".join(lines)


def run(claim: Claim, came_from: str, tools: dict, ask=None, max_steps: int = MAX_STEPS) -> dict | None:
    ask = ask or (lambda system, user: model.ask_json(system, user, max_tokens=500, timeout=60,
                                                      action="verifier_agent"))
    seen: list[dict] = []

    for _ in range(max_steps + 1):
        answer = ask(SYSTEM, turn(claim, came_from, seen))

        if not isinstance(answer, dict) or not answer:
            return None

        if "answer" in answer:
            # An answer of null is it saying it found nothing, which is a finish.
            proposal = answer.get("answer")
            return {"proposal": proposal if isinstance(proposal, dict) else {}, "seen": seen}

        name = answer.get("tool")
        tool = tools.get(name) if isinstance(name, str) else None

        if tool is None:
            seen.append(citations.note(name, {}, "no such tool"))
            continue

        args = answer.get("args") if isinstance(answer.get("args"), dict) else {}
        again = next((step for step in seen
                      if step["tool"] == name and step["args"] == args), None)

        if again is not None:
            seen.append(citations.note(name, args, "you already called this and it said the same thing. "
                                                   "Call something else, or answer."))
            continue

        try:
            result = tool(**args)
        except TypeError:
            seen.append(citations.note(name, args, "wrong arguments for this tool"))
            continue

        seen.append(citations.step(name, args, result, MAX_TOOL_CHARS))

    return None


def names_version(text, version: str) -> bool:
    """Whether the text names exactly this version: 1.7.1 is not 1.7.10, 11.7.1 or 1.7.1rc1."""
    wanted = re.escape(flat(version))
    return bool(wanted) and re.search(rf"(?<![\d.]){wanted}(?![\w]|\.\d|-\w)", flat(text)) is not None


def check(gathered: dict, version: str, came_from: str = "") -> dict | None:
    """A line and a link, both on one page the other party's tool returned, both naming
    this version exactly. The page matters most: the release we already hold, quoted back
    at us, is not a second record of anything, and neither is a line from one page pinned
    to a link from another."""
    proposal = (gathered or {}).get("proposal") or {}

    if proposal.get("found") is not True:
        return None

    quote = proposal.get("quote")
    url = str(proposal.get("url") or "").strip()

    if not url.startswith("http") or not names_version(quote, version):
        # A record that does not name this version is a second source for something else.
        return None

    other, tools = OTHER_PARTY.get(came_from), OTHER_TOOLS.get(came_from)

    if other and other not in flat(url):
        return None

    for step in (gathered or {}).get("seen") or []:
        name = citations.tool_name(step.get("tool"))

        if tools and name not in tools:
            continue

        if not citations.backed(quote, [step]):
            continue

        if flat(url) not in flat(step.get("text")) or citations.echoed(url, step):
            # A link that page never printed, or one the model wrote into the call itself.
            continue

        if name != "changelog" and not names_version(url, version):
            # A release page for some other version. A changelog is one file for every
            # version, so its link cannot name one; its line has to.
            continue

        return {"url": url, "quote": str(quote)[:220],
                "looked": [{"tool": s["tool"], "args": s.get("args", {})} for s in gathered["seen"]]}

    return None


def confirm(claim: Claim, came_from: str, tools: dict | None = None, ask=None,
            max_steps: int = MAX_STEPS) -> dict | None:
    """Where else this version is written down, or None when it is written nowhere else."""
    if not claim.version:
        return None

    gathered = run(claim, came_from, tools if tools is not None else tools_for(),
                   ask=ask, max_steps=max_steps)
    found = check(gathered, claim.version, came_from) if gathered else None

    trace.current.record("verifier_agent", 0, ok=found is not None, note=(
        f"{claim.subject} {claim.version}: "
        f"{'a second record at ' + found['url'] if found else 'no second record it could point at'}"))
    return found
