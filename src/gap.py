import re

NUMERIC_RE = re.compile(r"\d+")

UNKNOWN = "unknown"
UNPINNED = "unpinned"
DEPENDENCY = "dependency"
CURRENT = "current"
AHEAD = "ahead"
PATCH_ONLY = "patch_only"
BEHIND_MINOR = "behind_minor"
BEHIND_MAJOR = "behind_major"

ACTIONABLE = {BEHIND_MAJOR, BEHIND_MINOR, UNPINNED}


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


def compare(pinned: str | None, latest: str | None, unpinned: bool = False) -> str:
    if unpinned:
        return UNPINNED

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


def describe(subject: str, pinned: str | None, latest: str | None, kind: str,
             has_chapter: bool = True) -> str:
    if not has_chapter:
        if latest:
            return f"No chapter in the course installs or teaches {subject}. The newest confirmed release is {latest}."
        return f"No chapter in the course installs or teaches {subject}."

    if kind == UNPINNED:
        if latest:
            return (f"The notebooks install {subject} with no version bound, so a student today gets "
                    f"{latest} whatever the material was written against.")
        return f"The notebooks install {subject} with no version bound."

    if kind == DEPENDENCY:
        return (f"The chapter installs {subject} without a bound, but does not teach it. "
                f"That is a dependency to pin, not material to rewrite.")

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
           published: list, last_updated: str | None, unpinned: bool = False,
           legacy: list[dict] | None = None, has_chapter: bool = True,
           taught: bool = True) -> dict:
    latest = newest(versions)
    kind = compare(pinned, latest, unpinned)

    # Unbound is only a curriculum problem when the chapter teaches the package or
    # still calls something a later release removed. Otherwise it is a dependency
    # to pin, and saying "rewrite the chapter" would be noise.
    if kind == UNPINNED and not taught and not legacy:
        kind = DEPENDENCY

    return {
        "subject": subject,
        "pinned": pinned,
        "latest": latest,
        "kind": kind,
        "chapter_updated": last_updated,
        "released_since": count_after(published, last_updated),
        "sentence": describe(subject, pinned, latest, kind, has_chapter),
        "legacy": legacy or [],
        "taught": taught,
    }


def legacy_sentence(assessment: dict) -> str:
    markers = assessment["legacy"]

    if not markers:
        return ""

    names = [marker["uses"] for marker in markers[:4]]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"

    if len(names) == 1:
        return f"The notebooks still call {listed}, and our pattern table says {markers[0]['note']}."

    return (f"The notebooks still call {listed} - calls our pattern table marks as removed or "
            f"moved in a later major release.")


def staleness_sentence(assessment: dict) -> str:
    since = assessment["released_since"]
    updated = assessment["chapter_updated"]

    if not updated or since == 0:
        return ""

    return (f"{since} of the confirmed releases in this run landed after the chapter was "
            f"last updated on {updated}.")
