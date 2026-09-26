"""How ready the course is to teach something: maturity, prerequisites, difficulty.

These are the brief's teaching-feasibility factors, and they are kept out of the
priority. Priority says how much a change matters; feasibility says how ready the
course is to teach it. Folded into one number, an easy version pin outranked a
real change, and every decision threshold moved at once. Each factor is measured
from data the run holds, and says "default" when it cannot be.
"""

from datetime import datetime

from src import arabic, changes

FACTORS = ("maturity", "prerequisites", "difficulty")

# At or below this, a tool is not stable enough to teach yet. The brief names low
# maturity as the reason to watch.
IMMATURE = 2


def when(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value

    return datetime.fromisoformat(str(value))


def maturity(facts: dict | None, as_of: datetime, found: dict, newest: str | None) -> tuple[int, str, dict]:
    """1 to 5 from four checks against the package's whole history on PyPI: a year
    old, three years old, a 1.0 or later stable release, and a steady run with no
    breaking change in the notes and no pre-release as the newest version."""
    first = when((facts or {}).get("first_release"))

    if first is None:
        return 3, "default", {}

    age = round((as_of - first).days / 365, 1)
    stable = facts.get("latest_stable")
    head = (stable or "0").split(".")[0]
    major = int(head) if head.isdigit() else 0
    steady = not (found or {}).get("breaking") and not changes.is_prerelease(newest)
    checks = [age >= 1, age >= 3, major >= 1, steady]

    return 1 + sum(checks), "measured", {"first_release": first.date().isoformat(), "age_years": age,
                                          "latest_stable": stable, "major": major, "steady": steady}


def taught_packages(chapters: list[dict]) -> set[str]:
    """Packages a chapter installs and names in its own topics or tools."""
    from src.stages.stage4_act import teaches_package

    return {package for chapter in chapters
            for package in list(chapter.get("pins", {})) + chapter.get("installs_unpinned", [])
            if teaches_package(chapter, package)}


def family(subject: str) -> str:
    return subject.replace("_", "-").split("-")[0]


def prerequisites(subject: str, facts: dict | None, taught: set[str]) -> tuple[int, str, dict]:
    """5 when the course teaches the package itself, 4 when it teaches its family
    or something the package declares it builds on. Otherwise unmeasured: finding
    no link in the data is not the same as finding the background missing."""
    if subject in taught or (facts or {}).get("pypi") in taught:
        return 5, "measured", {"basis": "taught"}

    if family(subject) in {family(package) for package in taught}:
        return 4, "measured", {"basis": "family", "via": [family(subject)]}

    builds_on = [package for package in (facts or {}).get("requires", []) if package in taught]

    if builds_on:
        return 4, "measured", {"basis": "builds_on", "via": builds_on[:3]}

    return 3, "default", {}


def difficulty(chapter_id: str | None, found: dict, edits: list[dict], maturity_score: int) -> tuple[int, str, dict]:
    """How much work the teaching material needs, 1 easy to 5 hard. For material
    that exists: the import lines the release check lists, whether they reach
    several chapters, and any breaking change or deprecation to teach around. New
    material starts at 3, a notebook from nothing, and is 4 on a tool still settling."""
    found = found or {}

    if chapter_id is None:
        moving = maturity_score <= IMMATURE
        return 3 + moving, "measured", {"new_material": True, "moving": moving}

    lines = len(edits)
    chapters = len({edit["chapter_id"] for edit in edits})
    breaking, deprecation = found.get("breaking", 0), found.get("deprecation", 0)
    score = 1 + (lines >= 1) + (lines >= 20) + (chapters >= 2) + bool(breaking or deprecation)

    return min(score, 5), "measured", {"new_material": False, "edit_lines": lines, "chapters": chapters,
                                        "breaking": breaking, "deprecation": deprecation}


def score(dimensions: dict) -> float | None:
    """Feasibility on the same 1 to 5 scale: the mean of maturity, prerequisites and
    ease, where ease is 6 minus difficulty."""
    if not all(name in dimensions for name in FACTORS):
        return None

    return round((dimensions["maturity"] + dimensions["prerequisites"] + 6 - dimensions["difficulty"]) / 3, 1)


def immature(scored) -> bool:
    return scored.provenance.get("maturity") == "measured" and scored.dimensions.get("maturity", 3) <= IMMATURE


def explain(factor: str, value: int, provenance: str, detail: dict, subject: str) -> tuple[str, str]:
    """One factor's reason, in English and Arabic, from the facts it was measured from."""
    if factor == "maturity":
        if provenance != "measured":
            return "Not measured: PyPI holds no history for it.", "غير مقاس: لا سجل له في PyPI."

        stable = detail["latest_stable"]
        run_en = ("no breaking change and no pre-release in this run" if detail["steady"]
                  else "a breaking change or a pre-release in this run")
        run_ar = ("بلا تغيير كاسر ولا إصدار تجريبي في هذه التشغيلة" if detail["steady"]
                  else "فيها تغيير كاسر أو إصدار تجريبي في هذه التشغيلة")
        return (f"First released {detail['first_release']}, {detail['age_years']} years ago; newest stable "
                f"release {stable or 'none yet'}; {run_en}.",
                f"أول إصدار في {detail['first_release']}، قبل {detail['age_years']} سنة؛ أحدث إصدار مستقر "
                f"{stable or 'لا يوجد بعد'}؛ {run_ar}.")

    if factor == "prerequisites":
        basis = detail.get("basis")

        if basis == "taught":
            return f"The course already teaches {subject}.", f"يدرّس المقرر {subject} بالفعل."

        if basis == "family":
            return (f"The course teaches {detail['via'][0]}, the family {subject} belongs to.",
                    f"يدرّس المقرر {detail['via'][0]}، العائلة التي ينتمي إليها {subject}.")

        if basis == "builds_on":
            return (f"It builds on {', '.join(detail['via'])}, which the course teaches.",
                    f"يعتمد على {arabic.listed(detail['via'])}، وهي مما يدرّسه المقرر.")

        return ("Not measured: nothing links it to what the course teaches, which says nothing either way.",
                "غير مقاس: لا صلة ظاهرة بينه وبين ما يدرّسه المقرر، وهذا لا يثبت شيئاً في أي اتجاه.")

    if detail.get("new_material"):
        if detail.get("moving"):
            return "New material from scratch, on a tool still settling.", "مادة جديدة من الصفر، لأداة لم تستقر بعد."
        return "New material from scratch.", "مادة جديدة من الصفر."

    lines, chapters = detail["edit_lines"], detail["chapters"]
    breaking, deprecation = detail["breaking"], detail["deprecation"]

    if not lines and not breaking and not deprecation:
        return ("Nothing in the notebooks to rewrite; at most a version pin.",
                "لا شيء في النوتبوكات يُعاد كتابته، وأقصى ما يلزم تثبيت نسخة.")

    english, arabic_parts = [], []

    if lines:
        english.append(f"{lines} import line{'s' if lines != 1 else ''} to change across "
                       f"{chapters} chapter{'s' if chapters != 1 else ''}")
        arabic_parts.append(f"تغيير {arabic.counted(lines, arabic.LINE, oblique=True)} في "
                            f"{arabic.counted(chapters, arabic.CHAPTER, oblique=True)}")

    if breaking:
        english.append(f"{breaking} breaking change{'s' if breaking != 1 else ''} to teach around")
        arabic_parts.append(f"مراعاة {arabic.counted(breaking, arabic.BREAKING, oblique=True)} في الدرس")

    if deprecation:
        english.append("a deprecation to replace")
        arabic_parts.append("استبدال ما صار مهجوراً")

    return "; ".join(english) + ".", "، و".join(arabic_parts) + "."
