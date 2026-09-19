import re

NUMERIC_RE = re.compile(r"\d+")

UNKNOWN = "unknown"
CURRENT = "current"
AHEAD = "ahead"
PATCH_ONLY = "patch_only"
BEHIND_MINOR = "behind_minor"
BEHIND_MAJOR = "behind_major"

ACTIONABLE = {BEHIND_MAJOR, BEHIND_MINOR}


def parts(version: str | None) -> tuple[int, ...] | None:
    if not version:
        return None

    numbers = NUMERIC_RE.findall(version.split("+")[0])

    if not numbers:
        return None

    return tuple(int(n) for n in numbers[:3])


def padded(version: str | None) -> tuple[int, int, int] | None:
    found = parts(version)

    if found is None:
        return None

    return (found + (0, 0, 0))[:3]


def newest(versions: list[str | None]) -> str | None:
    ranked = [(padded(v), v) for v in versions if padded(v) is not None]

    if not ranked:
        return None

    return max(ranked)[1]


def compare(pinned: str | None, latest: str | None) -> str:
    taught = padded(pinned)
    released = padded(latest)

    if taught is None or released is None:
        return UNKNOWN

    if released == taught:
        return CURRENT

    if released < taught:
        return AHEAD

    if released[0] != taught[0]:
        return BEHIND_MAJOR

    if released[1] != taught[1]:
        return BEHIND_MINOR

    return PATCH_ONLY


def describe(subject: str, pinned: str | None, latest: str | None, kind: str) -> str:
    if kind == UNKNOWN:
        if latest:
            return f"The chapter does not record which {subject} version it teaches, so the distance to {latest} cannot be measured."
        return f"No released {subject} version was confirmed in this run."

    if kind == CURRENT:
        return f"The chapter teaches {subject} {pinned}, which is the newest confirmed release."

    if kind == AHEAD:
        return f"The chapter teaches {subject} {pinned}; nothing newer was confirmed in this run."

    if kind == PATCH_ONLY:
        return f"{subject} moved from {pinned} to {latest}: patch releases only, so the material still holds."

    if kind == BEHIND_MINOR:
        return f"{subject} moved from {pinned} to {latest}: a minor release, so the chapter may miss new behaviour."

    return f"{subject} moved from {pinned} to {latest}: a major release, so what the chapter teaches can be gone."


def count_after(published: list, since: str | None) -> int:
    if not since:
        return 0

    return sum(1 for date in published if date is not None and str(date)[:10] > since)


def assess(subject: str, versions: list[str | None], pinned: str | None,
           published: list, last_updated: str | None) -> dict:
    latest = newest(versions)
    kind = compare(pinned, latest)

    return {
        "subject": subject,
        "pinned": pinned,
        "latest": latest,
        "kind": kind,
        "chapter_updated": last_updated,
        "released_since": count_after(published, last_updated),
        "sentence": describe(subject, pinned, latest, kind),
    }


def staleness_sentence(assessment: dict) -> str:
    since = assessment["released_since"]
    updated = assessment["chapter_updated"]

    if not updated or since == 0:
        return ""

    return (f"{since} of the confirmed releases in this run landed after the chapter was "
            f"last updated on {updated}.")
