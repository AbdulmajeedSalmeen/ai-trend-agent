"""The first steps a teacher takes on each recommendation.

The brief asks for an initial action plan beside every recommendation. Each step
is built from facts the run already holds: the edit list, the version gap, what
the releases changed and what the market says. Which steps a plan has is decided
once, here, and each language only words them, so the Arabic plan and the English
plan always have the same steps in the same order.
"""

from collections import Counter

from src import arabic, feasibility, gap
from src.changes import is_prerelease

HIGHLIGHT_LIMIT = 80


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def highlight(score, kind: str) -> str | None:
    """The first release-note line of a kind, short enough for a step."""
    for line in (score.changes or {}).get("highlights", []):
        found, _, text = line.partition(":")

        if found.strip() == kind:
            text = text.strip()

            if len(text) > HIGHLIGHT_LIMIT:
                text = text[:HIGHLIGHT_LIMIT].rsplit(" ", 1)[0] + "…"

            return text

    return None


def chapter_order(chapter_id: str) -> int:
    return int(chapter_id[1:]) if chapter_id[1:].isdigit() else 0


def teachable(score) -> tuple[str, str] | None:
    """The change most worth a teacher's attention, strongest kind first."""
    for kind in ("breaking", "deprecation", "feature"):
        if (score.changes or {}).get(kind):
            text = highlight(score, kind)

            if text:
                return kind, text

    return None


# Steps that name a version to pin or run on. A pre-release is never one to teach
# on, so those steps point at the newest stable release instead.
PINNING = {"pin", "pin_guard", "pin_dependency", "bump", "bump_minor", "rerun"}


def steps(subject: str, score, action: str, assessment: dict, edits: list[dict]) -> list[tuple[str, dict]]:
    """Which steps the plan has, with the facts each one quotes: two at least,
    three at most. A plan with one step left to say ends on when to look again."""
    found = chosen(subject, score, action, assessment, edits)

    if len(found) < 2:
        found.append(("recheck_notes", {"subject": subject}))

    return [(key, {**facts, "prerelease": is_prerelease(facts.get("latest"))} if key in PINNING else facts)
            for key, facts in found[:3]]


def chosen(subject: str, score, action: str, assessment: dict, edits: list[dict]) -> list[tuple[str, dict]]:
    latest = assessment["latest"]
    kind = assessment["kind"]
    market = score.market or {}
    found = []

    if action == "investigate_larger_change":
        now = [edit for edit in edits if edit["runs_as_pinned"] is False]
        pinned = [edit for edit in edits if edit["runs_as_pinned"]]

        if now:
            found.append(("fix_now", {"lines": len(now), "notebooks": len({e["notebook"] for e in now}),
                                      "chapters": sorted({e["chapter_id"] for e in now}, key=chapter_order)}))

        if pinned:
            specs = [spec for spec, _ in Counter(edit["installs"] for edit in pinned).most_common()]
            found.append(("decide_line", {"subject": subject, "specs": specs, "latest": latest,
                                          "notebooks": len({e["notebook"] for e in pinned})}))

        found.append(("move_lines", {"lines": len(edits), "notebooks": len({e["notebook"] for e in edits}),
                                     "chapters": len({e["chapter_id"] for e in edits})}))
        return found[:3]

    if action == "update_existing_material":
        if edits:
            found.append(("change_lines", {"lines": len(edits), "notebooks": len({e["notebook"] for e in edits}),
                                           "chapter": score.chapter_id}))
        elif assessment["legacy"]:
            found.append(("legacy", {"uses": [marker["uses"] for marker in assessment["legacy"][:3]]}))

        if kind == gap.UNPINNED and latest:
            found.append(("pin", {"subject": subject, "latest": latest}))
        elif kind in (gap.BEHIND_MAJOR, gap.BEHIND_MINOR) and latest:
            found.append(("bump" if kind == gap.BEHIND_MAJOR else "bump_minor",
                          {"subject": subject, "pinned": assessment["pinned"], "latest": latest}))
        elif kind == gap.UNKNOWN:
            found.append(("record_version", {"subject": subject}))

        change = teachable(score)

        if change:
            found.append((change[0], {"highlight": change[1]}))

        if latest:
            found.append(("rerun", {"chapter": score.chapter_id, "subject": subject, "latest": latest}))

        return found[:3]

    if action in ("add_new_lesson", "add_optional_content"):
        found.append(("outline" if action == "add_new_lesson" else "optional",
                      {"subject": subject, "jobs": market.get("jobs"), "months": market.get("months", 3),
                       "installs": market.get("downloads")}))
        feature = highlight(score, "feature") or highlight(score, "breaking")

        if feature and latest:
            found.append(("build_on", {"latest": f"{subject} {latest}", "highlight": feature}))

        if action == "add_new_lesson":
            found.append(("review", {}))
        elif market.get("jobs") is not None:
            found.append(("promote", {"jobs": market["jobs"], "months": market.get("months", 3)}))

        return found[:3]

    # Watching: say what keeps the lesson safe meanwhile, and when to look again.
    if score.confidence < 0.5:
        return [("wait_confirm", {}), ("recheck_notes", {"subject": subject})]

    if feasibility.immature(score):
        return [("wait_stable", {"subject": subject}), ("recheck_notes", {"subject": subject})]

    if score.chapter_id is None:
        found = [("nothing_new", {})] if score.changes and not teachable(score) else []

        if market.get("jobs") is not None:
            found.append(("revisit_market", {"jobs": market["jobs"], "months": market.get("months", 3)}))

        return found + [("recheck_notes", {"subject": subject})]

    if kind == gap.PATCH_ONLY:
        return [("leave_patch", {}), ("recheck_minor", {"subject": subject, "latest": latest})]

    if kind == gap.UNPINNED and latest:
        return [("pin_guard", {"subject": subject, "latest": latest}), ("recheck_notes", {"subject": subject})]

    if kind == gap.DEPENDENCY and latest:
        return [("pin_dependency", {"subject": subject, "latest": latest}), ("leave_dependency", {})]

    if kind == gap.BEHIND_MINOR:
        return [("leave_pinned", {"pinned": f"{subject} {assessment['pinned']}"}),
                ("recheck_major", {"subject": subject})]

    if kind in (gap.CURRENT, gap.AHEAD):
        return [("leave_current", {}), ("recheck_notes", {"subject": subject})]

    return [("record_version", {"subject": subject}), ("recheck_notes", {"subject": subject})]


def demand(facts: dict) -> str:
    parts = []

    if facts.get("jobs") is not None:
        parts.append(f"{plural(facts['jobs'], 'job post')} in {facts['months']} months")

    if facts.get("installs") is not None:
        parts.append(f"{readable(facts['installs'])} installs last month")

    return ", ".join(parts)


def readable(count: int) -> str:
    from src.stages.stage4_act import readable as spelled_out

    return spelled_out(count)


def english(key: str, facts: dict) -> str:
    if facts.get("prerelease"):
        return english_stable(key, facts)

    if key == "fix_now":
        return (f"First fix what breaks on today's install: {plural(facts['lines'], 'import line')} in "
                f"{plural(facts['notebooks'], 'notebook')} ({', '.join(facts['chapters'])}).")

    if key == "decide_line":
        verb = "pins" if facts["notebooks"] == 1 else "pin"
        return (f"Decide once, for the whole course: stay on the {facts['subject']} line "
                f"{plural(facts['notebooks'], 'notebook')} {verb} ({', '.join(facts['specs'])}), "
                f"or move to {facts['subject']} {facts['latest']}.")

    if key == "move_lines":
        return (f"To move, change {plural(facts['lines'], 'import line')} in {plural(facts['notebooks'], 'notebook')} "
                f"across {plural(facts['chapters'], 'chapter')}; the edit list names each cell.")

    if key == "change_lines":
        return (f"Change {plural(facts['lines'], 'import line')} in {plural(facts['notebooks'], 'notebook')} "
                f"of {facts['chapter']}; the edit list names each cell.")

    if key == "legacy":
        return f"Replace the calls the release removed: {', '.join(facts['uses'])}."

    if key == "pin":
        return f"Pin {facts['subject']}=={facts['latest']} in the install cell, so the notebook runs as written."

    if key == "bump":
        return (f"Move the pin from {facts['subject']} {facts['pinned']} to {facts['latest']}, "
                f"then fix what the major release changed.")

    if key == "bump_minor":
        return f"Move the pin from {facts['subject']} {facts['pinned']} to {facts['latest']}."

    if key == "breaking":
        return f"Check the lesson against this breaking change: {facts['highlight']}."

    if key == "deprecation":
        return f"Replace what the release deprecates: {facts['highlight']}."

    if key == "feature":
        return f"Consider a short section on what is new: {facts['highlight']}."

    if key == "rerun":
        return f"Run the {facts['chapter']} notebooks on {facts['subject']} {facts['latest']} before the next cohort."

    if key == "outline":
        found = demand(facts)
        return f"Outline a lesson on {facts['subject']}: {found}." if found else \
            f"Outline a lesson on {facts['subject']} and where it fits in the course."

    if key == "optional":
        return f"Add an optional notebook on {facts['subject']}, outside the core path."

    if key == "build_on":
        return f"Build the notebook around what {facts['latest']} adds: {facts['highlight']}."

    if key == "review":
        return "Flag it for instructor review before the next cohort."

    if key == "promote":
        if facts["jobs"] == 0:
            return f"Make it a lesson once employers ask for it; no job post named it in {facts['months']} months."
        return (f"Make it a lesson once more employers ask for it; "
                f"{plural(facts['jobs'], 'job post')} named it in {facts['months']} months.")

    if key == "wait_confirm":
        return "Wait for an official release to confirm the claims before acting."

    if key == "wait_stable":
        return f"Revisit once {facts['subject']} has a stable release and a year of history."

    if key == "recheck_notes":
        return f"Read the notes of the next {facts['subject']} release before the next cohort."

    if key == "nothing_new":
        return "Nothing to add: the releases only fix and maintain."

    if key == "revisit_market":
        if facts["jobs"] == 0:
            return f"Revisit when employers ask for it; no job post named it in {facts['months']} months."
        return (f"Revisit when more employers ask for it; "
                f"{plural(facts['jobs'], 'job post')} named it in {facts['months']} months.")

    if key == "leave_patch":
        return "Leave the chapter as it is: the releases since its version are patches."

    if key == "recheck_minor":
        return f"Check again when {facts['subject']} ships a minor or major release after {facts['latest']}."

    if key == "pin_guard":
        return (f"Pin {facts['subject']}=={facts['latest']} in the install cell, "
                f"so the next release cannot change the lesson.")

    if key == "pin_dependency":
        return f"Pin {facts['subject']}=={facts['latest']} in the install cell; the lesson itself needs no change."

    if key == "leave_dependency":
        return "Leave the lesson as it is: the chapter installs it but does not teach it."

    if key == "leave_pinned":
        return f"Leave the chapter as it is: the notebook pins {facts['pinned']} and runs as written."

    if key == "recheck_major":
        return f"Check again when {facts['subject']} ships a major release."

    if key == "leave_current":
        return "Leave the chapter as it is: it teaches the newest confirmed release."

    if key == "record_version":
        return f"Record which {facts['subject']} version the chapter uses, so the next run can measure the gap."

    raise KeyError(key)


def english_stable(key: str, facts: dict) -> str:
    """A pinning step whose newest confirmed version is a pre-release."""
    beta = f"{facts['latest']} is a pre-release"

    if key in ("pin", "pin_guard", "pin_dependency"):
        return f"Pin {facts['subject']} to its newest stable release in the install cell; {beta}."

    if key in ("bump", "bump_minor"):
        return f"Move the pin from {facts['subject']} {facts['pinned']} to its newest stable release; {beta}."

    return (f"Run the {facts['chapter']} notebooks on the newest stable {facts['subject']} "
            f"before the next cohort; {beta}.")


def build(subject: str, score, action: str, assessment: dict, edits: list[dict]) -> tuple[list[str], list[str]]:
    """The plan in English and in Arabic, step for step."""
    chosen = steps(subject, score, action, assessment, edits)
    installs = (score.market or {}).get("downloads")
    spelled = readable(installs) if installs is not None else None

    return ([english(key, facts) for key, facts in chosen],
            [arabic.plan_step(key, facts, spelled) for key, facts in chosen])
