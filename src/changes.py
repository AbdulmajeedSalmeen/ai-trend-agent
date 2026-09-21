"""What a release actually changed, read from its notes.

A version number says something shipped. It does not say whether a teacher should
care. Four in five lines of the release notes we collect are chores; a bootcamp
needs to know about the breaking change and the new concept, not the dependency
bump. This reads the notes and sorts every line into the kind of change it is.

Release notes arrive in four shapes, and all four are handled:
  - one conventional commit per line:   "feat(langgraph): expose trace_policy"
  - release-please sections:            "### Features" then bullets
  - GitHub's generated sections:        "### 🚀 Features" then bullets
  - plain sections:                     "### Bug Fixes" then bullets
"""

import re

PREFIX_RE = re.compile(r"^\s*(?:[*\-]\s*)?(?P<type>[a-z][a-z0-9_]*)(?:\([^)]*\))?(?P<bang>!)?:\s*(?P<text>.+)$", re.I)
HEADING_RE = re.compile(r"^\s*#{2,6}\s*(?P<text>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[*\-]\s+(?P<text>.+)$")

# Conventional commit types, and the kind of change each one is.
TYPES = {
    "feat": "feature", "feature": "feature",
    "fix": "fix", "bugfix": "fix", "hotfix": "fix",
    "perf": "fix",
    "chore": "noise", "ci": "noise", "build": "noise", "docs": "noise", "doc": "noise",
    "test": "noise", "tests": "noise", "style": "noise", "refactor": "noise",
    "release": "noise", "revert": "noise", "deps": "noise", "qa": "noise",
}

# Section headings, matched on a word, whatever emoji or wording sits around it.
SECTIONS = [
    ("breaking", "breaking"),
    ("deprecat", "deprecation"),
    ("feature", "feature"), ("new", "feature"), ("added", "feature"), ("enhancement", "feature"),
    ("bug", "fix"), ("fix", "fix"), ("performance", "fix"), ("security", "fix"),
    ("chore", "noise"), ("documentation", "noise"), ("docs", "noise"), ("depend", "noise"),
    ("refactor", "noise"), ("test", "noise"), ("build", "noise"), ("ci", "noise"),
    ("maintenance", "noise"), ("internal", "noise"),
]

KINDS = ("breaking", "deprecation", "feature", "fix", "noise", "other")

# What earns a teacher's attention, strongest first. A fix or a chore never does.
TEACHABLE = ("breaking", "deprecation", "feature")

ADDITION_RE = re.compile(r"^(add|adds|added|support|supports|introduce|introduces|new|enable|expose)\b", re.I)
DEPRECATION_RE = re.compile(r"\bdeprecat", re.I)
BREAKING_TEXT = re.compile(r"\bbreaking change\b", re.I)
REMOVAL_TEXT = re.compile(
    r"\b(remove|removes|removed|drop|drops|dropped)\b.*\b(support|api|argument|parameter|method|class|function|module)\b",
    re.I,
)
PRERELEASE_RE = re.compile(r"\d(a|b|rc|dev|alpha|beta)\d*$", re.I)

NOISE_TEXT = re.compile(r"^(bump|update) .*(dependenc|version|group)|^release\b", re.I)


def clean(text: str) -> str:
    """The change itself, without the PR number, the author or the markdown."""
    text = re.sub(r"\s+by @\S+.*$", "", text)
    text = re.sub(r"\s*\(\[?#\d+\]?(\([^)]*\))?\)", "", text)
    text = re.sub(r"\s*\(#\d+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r":[a-z0-9_+\-]+:", "", text)
    text = re.sub(r"\s*\([0-9a-f]{7,40}\)", "", text)
    text = re.sub(r"^[^\w`(\[]+", "", text)
    return " ".join(text.split()).strip(" -:")


def section_kind(heading: str) -> str | None:
    lower = heading.lower()

    for word, kind in SECTIONS:
        if word in lower:
            return kind

    return None


def line_kind(line: str, section: str | None) -> tuple[str, str] | None:
    """The kind of change a single line records, and its text. None for a line
    that records nothing, such as a heading or a blank."""
    prefixed = PREFIX_RE.match(line)

    if prefixed and prefixed.group("type").lower() in TYPES:
        text = clean(prefixed.group("text"))
        kind = TYPES[prefixed.group("type").lower()]

        if prefixed.group("bang"):
            kind = "breaking"
        elif kind == "feature" and DEPRECATION_RE.search(text):
            kind = "deprecation"

        return kind, text

    bullet = BULLET_RE.match(line)

    if bullet is None:
        # A conventional prefix the table does not know, such as a transformers
        # model name: an addition is a feature, anything else is left unsorted.
        if prefixed:
            text = clean(prefixed.group("text"))
            return ("feature" if ADDITION_RE.match(text) else "other"), text
        return None

    text = clean(bullet.group("text"))

    if not text:
        return None

    if section in ("breaking", "deprecation"):
        return section, text

    if section == "feature" and DEPRECATION_RE.search(text):
        return "deprecation", text

    if section is not None:
        return section, text

    if NOISE_TEXT.search(text):
        return "noise", text

    return ("feature" if ADDITION_RE.match(text) else "other"), text


def promote(kind: str, text: str) -> tuple[str, str]:
    """A line that says it breaks something is breaking, whatever section it sat in.

    A fix is never promoted for removing something: taking out the argument that
    caused a bug is still a fix to the person reading it. A feature or an
    unsorted line that removes support or an API is not.
    """
    if BREAKING_TEXT.search(text):
        return "breaking", text

    if kind in ("feature", "other") and REMOVAL_TEXT.search(text):
        return "breaking", text

    return kind, text


def classify(notes: str) -> dict:
    """Count every kind of change in a set of release notes and keep the ones a
    teacher would read."""
    counts = {kind: 0 for kind in KINDS}
    highlights: list[tuple[str, str]] = []
    section = None

    for raw in (notes or "").splitlines():
        heading = HEADING_RE.match(raw)

        if heading:
            section = section_kind(heading.group("text"))
            continue

        found = line_kind(raw, section)

        if found is None:
            continue

        kind, text = promote(*found)
        counts[kind] += 1

        if kind in TEACHABLE and len(text) > 8:
            highlights.append((kind, text))

    order = {kind: index for index, kind in enumerate(TEACHABLE)}
    highlights.sort(key=lambda item: order[item[0]])

    return {**counts, "highlights": [f"{kind}: {text}" for kind, text in highlights[:6]]}


def is_prerelease(version: str | None) -> bool:
    return bool(version and PRERELEASE_RE.search(version))


def combine(summaries: list[dict]) -> dict:
    """Several releases of one package, read as one body of change."""
    total = {kind: 0 for kind in KINDS}
    highlights: list[str] = []

    for summary in summaries:
        for kind in KINDS:
            total[kind] += summary.get(kind, 0)

        for line in summary.get("highlights", []):
            if line not in highlights:
                highlights.append(line)

    order = {kind: index for index, kind in enumerate(TEACHABLE)}
    highlights.sort(key=lambda line: order.get(line.split(":", 1)[0], 9))
    total["highlights"] = highlights[:6]
    total["teachable"] = sum(total[kind] for kind in TEACHABLE)
    total["lines"] = sum(total[kind] for kind in KINDS)

    return total


def weight(summary: dict) -> int:
    """Impact on a 1 to 5 scale, from what changed rather than how often.

    A package that ships ten alphas of chores a week scored above one that
    changed a concept once, when impact was a count of releases.
    """
    if summary.get("breaking"):
        return 5

    if summary.get("deprecation"):
        return 4

    features = summary.get("feature", 0)

    if features >= 3:
        return 4

    if features:
        return 3

    if summary.get("fix"):
        return 2

    return 1
