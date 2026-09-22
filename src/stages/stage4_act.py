import json
import re
from pathlib import Path

from src import arabic, gap, memory, plan, runio
from src.reading import write_recommendation
from src.schema import Recommendation, Score, Signal, Trend

CURRICULUM_PATH = Path("fixtures/curriculum.json")


# A new lesson costs a teacher weeks to write. It needs employers asking for the
# tool, not only a tool existing. 3 on the market scale is roughly five job posts
# over three months, or a million installs a month.
NEW_LESSON_MARKET_FLOOR = 3

# Below that, a tool some employers already name is worth optional material: an
# elective a teacher can offer without rewriting the core path.
OPTIONAL_MARKET_FLOOR = 2


def teachable_changes(score: Score) -> int:
    found = score.changes or {}
    return found.get("breaking", 0) + found.get("deprecation", 0) + found.get("feature", 0)


def maintenance_only(score: Score) -> bool:
    """The releases were read, and nothing in them is worth teaching."""
    return bool(score.changes) and teachable_changes(score) == 0


def market_wants_it(score: Score) -> bool | None:
    """True or False when the market was measured, None when it could not be."""
    if score.provenance.get("market_relevance") != "measured":
        return None

    return score.dimensions.get("market_relevance", 0) >= NEW_LESSON_MARKET_FLOOR


def decide_action(score: Score, assessment: dict | None = None, chapters_affected: int = 0) -> str:
    if score.confidence < 0.5:
        return "watch"

    # A release that removed names the notebooks import in several chapters is
    # one decision for the whole course, not an edit per chapter.
    if chapters_affected >= 2:
        return "investigate_larger_change"

    if score.chapter_id is None:
        if maintenance_only(score):
            return "watch"

        if market_wants_it(score) is False:
            some_demand = score.dimensions.get("market_relevance", 0) >= OPTIONAL_MARKET_FLOOR
            worth_it = some_demand and teachable_changes(score) > 0 and score.priority >= 2.5
            return "add_optional_content" if worth_it else "watch"

        return "add_new_lesson" if score.priority >= 2.5 else "watch"

    if assessment is not None:
        # An unbound install has no version to measure against, so something
        # other than the version has to justify a rewrite: a removed API the
        # notebook still calls, or a breaking change or new concept read out of
        # the release notes. Without either, "a newer version exists" is the
        # only reason left, and a version number is evidence, never a reason.
        # Without this, six unbound PyPI-only packages with no notes at all were
        # sent to "update the chapter" on the strength of their version alone.
        if assessment["kind"] == gap.UNPINNED and not assessment["legacy"] and teachable_changes(score) == 0:
            return "watch"

        # A pinned notebook runs for the student exactly as it was written, so a
        # minor-version gap on its own breaks nothing. It takes a breaking change,
        # a deprecation or a new concept in the notes to make the gap matter. A
        # major gap is different: semver says a major release breaks things.
        if assessment["kind"] == gap.BEHIND_MINOR and not assessment["legacy"] and teachable_changes(score) == 0:
            return "watch"

        if assessment["kind"] in gap.ACTIONABLE:
            return "update_existing_material"

        if assessment["kind"] != gap.UNKNOWN:
            return "watch"

        if assessment["released_since"] >= 3 and score.priority >= 3.0:
            return "update_existing_material"

        return "watch"

    return "update_existing_material" if score.priority >= 3.0 else "watch"


def change_sentence(score: Score) -> str:
    """What the releases changed, in the terms a teacher decides by."""
    found = score.changes or {}

    if not found:
        return ""

    highlights = [line.split(":", 1)[1].strip() for line in found.get("highlights", [])[:2]]
    named = f" ({'; '.join(highlights)})" if highlights else ""

    if found.get("breaking"):
        return f"The releases include {found['breaking']} breaking change{'s' if found['breaking'] > 1 else ''}{named}."

    if found.get("deprecation"):
        return f"The releases deprecate something{named}."

    if found.get("feature"):
        count = found["feature"]
        return f"The releases add {count} new feature{'s' if count > 1 else ''}{named}."

    return (f"The releases are maintenance only: {found.get('fix', 0)} fixes and "
            f"{found.get('noise', 0)} chores, nothing new to teach.")


def market_sentence(score: Score, subject: str) -> str:
    """Whether employers ask for it, from the hiring threads and PyPI."""
    found = score.market or {}
    jobs, downloads = found.get("jobs"), found.get("downloads")

    if jobs is None and downloads is None:
        return ""

    parts = []

    if jobs is not None:
        term = found.get("job_term") or subject
        months = found.get("months", 3)
        parts.append(f"{jobs} job post{'s' if jobs != 1 else ''} named {term} in the last {months} months")

    if downloads is not None:
        parts.append(f"{readable(downloads)} installs last month")

    sentence = " and ".join(parts)
    sentence = sentence[0].upper() + sentence[1:] + "."

    if market_wants_it(score) is False:
        sentence += " Few employers ask for it yet."

    return sentence


def readable(count: int) -> str:
    for size, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if count >= size:
            return f"{count / size:.1f}{suffix}".replace(".0", "")

    return str(count)


CLOSINGS = {
    "weak": "Not acted on: the claims are too weak to trust.",
    "patch_only": "Nothing to rewrite yet.",
    "unpinned": ("Nothing read from its releases shows that it breaks what the chapter teaches "
                 "or adds something worth teaching, so there is nothing to rewrite. Pinning the "
                 "version in the notebook keeps it that way."),
    "behind_minor": ("The notebook pins its version, so it runs for a student exactly as written, "
                     "and nothing read from the releases shows the approach it teaches has changed."),
    "not_wanted": "Not a new lesson until more employers ask for it.",
    "optional": "Worth optional material, not a core lesson, until more employers ask for it.",
    "course_wide": "The same release reaches beyond this chapter: plan the move once, for the whole course.",
}


def closing_for(score: Score, action: str, assessment: dict) -> str | None:
    """Which closing a reason gets. Decided once for both languages."""
    if action == "investigate_larger_change":
        return "course_wide"

    if action == "add_optional_content":
        return "optional"

    if action != "watch":
        return None

    if score.confidence < 0.5:
        return "weak"

    if assessment["kind"] == gap.PATCH_ONLY:
        return "patch_only"

    if assessment["kind"] == gap.UNPINNED:
        return "unpinned"

    if assessment["kind"] == gap.BEHIND_MINOR:
        return "behind_minor"

    if score.chapter_id is None and market_wants_it(score) is False:
        return "not_wanted"

    return None


def spread_sentence(subject: str, latest: str, notebooks: int, chapters: int) -> str:
    return (f"Across the course, {plan.plural(notebooks, 'notebook')} in {plan.plural(chapters, 'chapter')} "
            f"import names that {subject} {latest} no longer has.")


def build_rationale(trend: Trend, score: Score, action: str,
                    assessment: dict | None = None, chapter: dict | None = None,
                    lang: str = "en", edits: list[dict] | None = None) -> str:
    """The rules' reason, in English or Arabic.

    Which sentences a reason holds, in what order, and which closing it ends
    on are decided here once, for both languages. Only the wording differs, so
    the Arabic cannot say something the English does not.
    """
    confirmed = sum(1 for claim in trend.claims if claim.verdict == "confirmed")
    unverified = len(trend.claims) - confirmed
    ar = lang == "ar"

    if assessment is None:
        if ar:
            return arabic.fallback(trend.subject, confirmed, unverified, score.priority,
                                   score.confidence, score.chapter_id)
        where = f"chapter {score.chapter_id}" if score.chapter_id else "no matching chapter"
        weak = " Not acted on: evidence too weak." if score.confidence < 0.5 else ""
        return (f"{trend.subject}: {confirmed} confirmed, {unverified} unverified. "
                f"Priority {score.priority:.2f}, Confidence {score.confidence:.2f}, {where}.{weak}")

    if ar:
        downloads = (score.market or {}).get("downloads")
        sentence = arabic.describe(trend.subject, assessment["pinned"], assessment["latest"],
                                   assessment["kind"], has_chapter=score.chapter_id is not None)
        changed = arabic.change_sentence(score.changes or {})
        demand = arabic.market_sentence(score.market or {}, trend.subject,
                                        readable(downloads) if downloads is not None else None,
                                        market_wants_it(score))
        legacy = arabic.legacy_sentence(assessment)
        stale = arabic.staleness_sentence(assessment)
        opening = arabic.chapter_opening(score.chapter_id, chapter.get("teaches_ar")) if chapter else ""
    else:
        sentence = assessment["sentence"]
        changed = change_sentence(score)
        demand = market_sentence(score, trend.subject)
        legacy = gap.legacy_sentence(assessment)
        stale = gap.staleness_sentence(assessment)
        opening = f"Chapter {score.chapter_id} teaches: {chapter['teaches']}" if chapter else ""

    spread = ""

    if action == "investigate_larger_change" and edits and assessment["latest"]:
        counts = (trend.subject, assessment["latest"], len({edit["notebook"] for edit in edits}),
                  len({edit["chapter_id"] for edit in edits}))
        spread = arabic.spread_sentence(*counts) if ar else spread_sentence(*counts)

    if score.chapter_id is None:
        parts = [sentence, changed, demand]
    else:
        parts = [opening, sentence, legacy, spread, changed, demand, stale]

    closing = closing_for(score, action, assessment)

    if closing:
        parts.append(arabic.CLOSINGS[closing] if ar else CLOSINGS[closing])

    parts.append(arabic.counts_line(confirmed, unverified, score.priority) if ar
                 else f"{confirmed} confirmed, {unverified} unverified, priority {score.priority:.2f}.")

    return " ".join(part for part in parts if part)


def required_facts(assessment: dict) -> list[str]:
    facts = [assessment["latest"]]

    if assessment["legacy"]:
        facts.append(assessment["legacy"][0]["uses"])

    return [fact for fact in facts if fact]


def load_chapters() -> dict:
    data = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    return {chapter["chapter_id"]: chapter for chapter in data["chapters"]}


def teaches_package(chapter: dict, subject: str) -> bool:
    """Named in the chapter's own topics or tool list, rather than installed as a
    dependency nobody talks about."""
    text = " ".join(chapter.get("topics_covered", []) + chapter.get("tools_covered", [])
                    + [chapter.get("title", "")]).lower()
    root = subject.replace("_", "-").split("-")[0]

    return root in re.findall(r"[a-z0-9]+", text)


def verified_markers(edits: list[dict]) -> list[dict]:
    """The names a chapter's notebooks import from a path the release no longer
    has, one marker each, in the shape the gap check reads."""
    markers, seen = [], set()

    for edit in edits:
        if not edit["moved_to"]:
            continue

        for name in edit["names"]:
            if name not in seen:
                seen.add(name)
                markers.append({"package": edit["package"], "uses": name, "checked": edit["checked"],
                                "module": edit["moved_to"][0]["module"], "verified": True})

    return markers


def assess_trend(trend: Trend, chapter: dict | None, published: dict, edits: list[dict] | None = None) -> dict:
    confirmed = [claim for claim in trend.claims if claim.verdict == "confirmed"]
    has_chapter = chapter is not None
    chapter = chapter or {}
    legacy = [marker for marker in chapter.get("legacy_api", [])
              if marker["package"] == trend.subject] + verified_markers(edits or [])

    return gap.assess(
        trend.subject,
        [claim.version for claim in confirmed],
        chapter.get("pins", {}).get(trend.subject),
        [published.get(claim.source_signal_id) for claim in confirmed],
        chapter.get("last_updated"),
        unpinned=trend.subject in chapter.get("installs_unpinned", []),
        legacy=legacy,
        has_chapter=has_chapter,
        taught=teaches_package(chapter, trend.subject) if has_chapter else True,
    )


def course_edits(chapters: dict) -> dict[str, list[dict]]:
    """Every checked edit in the curriculum, by the package whose release it answers to."""
    found: dict[str, list[dict]] = {}

    for chapter in chapters.values():
        for edit in chapter.get("material_edits", []):
            found.setdefault(edit["package"], []).append(edit)

    return found


def decide(trend: Trend, score: Score, chapters: dict, published: dict, edits_by_package: dict) -> dict:
    """Everything the rules decide about one trend. A new run and a redecided saved
    run both come through here, so they cannot disagree."""
    chapter = chapters.get(score.chapter_id)
    edits = edits_by_package.get(trend.subject, [])
    own = [edit for edit in edits if edit["chapter_id"] == score.chapter_id]
    assessment = assess_trend(trend, chapter, published, own)
    action = decide_action(score, assessment, chapters_affected=len({edit["chapter_id"] for edit in edits}))

    # A course-wide decision shows every line it covers; a chapter update only its own.
    if action != "investigate_larger_change":
        edits = own

    steps, steps_ar = plan.build(trend.subject, score, action, assessment, edits)

    return {"chapter": chapter, "assessment": assessment, "action": action, "edits": edits,
            "action_plan": steps, "action_plan_ar": steps_ar}


def run(run_dir: Path) -> None:
    trends = runio.load_artifact(run_dir, "trends", Trend)
    scores = runio.load_artifact(run_dir, "scores", Score)
    signals = runio.load_artifact(run_dir, "signals", Signal)
    chapters = load_chapters()
    edits_by_package = course_edits(chapters)

    published = {signal.id: signal.published_at.isoformat() for signal in signals}
    scores_by_trend = {score.trend_id: score for score in scores}
    past = memory.history(run_dir.name)

    recommendations = []
    skipped = 0

    for trend in trends:
        score = scores_by_trend.get(trend.id)

        if score is None:
            skipped += 1
            continue

        decided = decide(trend, score, chapters, published, edits_by_package)
        chapter, assessment, action = decided["chapter"], decided["assessment"], decided["action"]

        confirmed = sum(1 for claim in trend.claims if claim.verdict == "confirmed")
        written = write_recommendation(
            trend.subject, action, score.chapter_id,
            confirmed, len(trend.claims) - confirmed, score.priority,
            teaches=chapter["teaches"] if chapter else None,
            gap_sentence=assessment["sentence"],
            legacy=gap.legacy_sentence(assessment),
            changed=change_sentence(score),
            demand=market_sentence(score, trend.subject),
            staleness=gap.staleness_sentence(assessment),
            claim_texts=[claim.text for claim in trend.claims],
            must_mention=required_facts(assessment),
        )

        recalled = memory.recall(trend.subject, action, assessment["latest"], past)

        recommendations.append(
            Recommendation(
                trend_id=trend.id,
                action=action,
                chapter_id=score.chapter_id,
                rationale=written or build_rationale(trend, score, action, assessment, chapter,
                                                     edits=decided["edits"]),
                rationale_by="model" if written else "rules",
                rationale_ar=build_rationale(trend, score, action, assessment, chapter, lang="ar",
                                             edits=decided["edits"]),
                action_plan=decided["action_plan"],
                action_plan_ar=decided["action_plan_ar"],
                edits=decided["edits"],
                chapter_version=assessment["pinned"],
                latest_version=assessment["latest"],
                gap_kind=assessment["kind"],
                releases_since=assessment["released_since"],
                legacy_uses=[marker["uses"] for marker in assessment["legacy"]],
                **recalled,
            )
        )

    runio.save_artifact(run_dir, "recommendations", recommendations)

    repeats = sum(1 for rec in recommendations if rec.runs_flagged > 1)
    print(f"{len(recommendations)} recommendations, {skipped} trends skipped, {repeats} repeated from earlier runs")


def redecide(run_dir: Path) -> dict[str, tuple[str, str]]:
    """Run the decision again over a saved run, with the rules as they are now.

    Calls no model. Every field the rules own is rebuilt: the action, the Arabic
    reason, the plan, the edit list and any English reason the rules wrote. A
    reason the model wrote is kept only where the action it explains still
    stands; elsewhere the rules' reason takes its place. What the run remembered about earlier runs is left as it was.
    Returns the actions that changed, by subject.
    """
    trends = {trend.id: trend for trend in runio.load_artifact(run_dir, "trends", Trend)}
    scores = {score.trend_id: score for score in runio.load_artifact(run_dir, "scores", Score)}
    signals = runio.load_artifact(run_dir, "signals", Signal)
    recommendations = runio.load_artifact(run_dir, "recommendations", Recommendation)
    chapters = load_chapters()
    edits_by_package = course_edits(chapters)
    published = {signal.id: signal.published_at.isoformat() for signal in signals}

    rebuilt, changed = [], {}

    for rec in recommendations:
        trend, score = trends.get(rec.trend_id), scores.get(rec.trend_id)

        if trend is None or score is None:
            rebuilt.append(rec)
            continue

        decided = decide(trend, score, chapters, published, edits_by_package)
        action, assessment, chapter, edits = (decided["action"], decided["assessment"],
                                              decided["chapter"], decided["edits"])

        if action != rec.action:
            changed[trend.subject] = (rec.action, action)

        # The rules' own English is always rebuilt. The model's is kept while the
        # action it explains stands, since no model is asked here to rewrite it.
        keep = action == rec.action and rec.rationale_by != "rules"

        rebuilt.append(rec.model_copy(update={
            "action": action,
            "rationale": rec.rationale if keep
            else build_rationale(trend, score, action, assessment, chapter, edits=edits),
            "rationale_by": rec.rationale_by if keep else "rules",
            "rationale_ar": build_rationale(trend, score, action, assessment, chapter, lang="ar", edits=edits),
            "action_plan": decided["action_plan"],
            "action_plan_ar": decided["action_plan_ar"],
            "edits": edits,
            "chapter_version": assessment["pinned"],
            "latest_version": assessment["latest"],
            "gap_kind": assessment["kind"],
            "releases_since": assessment["released_since"],
            "legacy_uses": [marker["uses"] for marker in assessment["legacy"]],
        }))

    runio.save_artifact(run_dir, "recommendations", rebuilt)
    return changed
