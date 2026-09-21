import json
import re
from pathlib import Path

from src import gap, memory, runio
from src.reading import write_recommendation
from src.schema import Recommendation, Score, Signal, Trend

CURRICULUM_PATH = Path("fixtures/curriculum.json")


# A new lesson costs a teacher weeks to write. It needs employers asking for the
# tool, not only a tool existing. 3 on the market scale is roughly five job posts
# over three months, or a million installs a month.
NEW_LESSON_MARKET_FLOOR = 3


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


def decide_action(score: Score, assessment: dict | None = None) -> str:
    if score.confidence < 0.5:
        return "watch"

    if score.chapter_id is None:
        if market_wants_it(score) is False or maintenance_only(score):
            return "watch"

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


def build_rationale(trend: Trend, score: Score, action: str,
                    assessment: dict | None = None, chapter: dict | None = None) -> str:
    confirmed = sum(1 for claim in trend.claims if claim.verdict == "confirmed")
    unverified = len(trend.claims) - confirmed

    if assessment is None:
        where = f"chapter {score.chapter_id}" if score.chapter_id else "no matching chapter"
        weak = " Not acted on: evidence too weak." if score.confidence < 0.5 else ""
        return (f"{trend.subject}: {confirmed} confirmed, {unverified} unverified. "
                f"Priority {score.priority:.2f}, Confidence {score.confidence:.2f}, {where}.{weak}")

    if score.chapter_id is None:
        parts = [assessment["sentence"], change_sentence(score), market_sentence(score, trend.subject)]
    else:
        opening = f"Chapter {score.chapter_id} teaches: {chapter['teaches']}" if chapter else ""
        parts = [opening, assessment["sentence"], gap.legacy_sentence(assessment),
                 change_sentence(score), market_sentence(score, trend.subject),
                 gap.staleness_sentence(assessment)]

    if action == "watch" and score.confidence < 0.5:
        parts.append("Not acted on: the claims are too weak to trust.")
    elif action == "watch" and assessment["kind"] == gap.PATCH_ONLY:
        parts.append("Nothing to rewrite yet.")
    elif action == "watch" and assessment["kind"] == gap.UNPINNED:
        parts.append("Nothing read from its releases shows that it breaks what the chapter teaches "
                     "or adds something worth teaching, so there is nothing to rewrite. Pinning the "
                     "version in the notebook keeps it that way.")
    elif action == "watch" and assessment["kind"] == gap.BEHIND_MINOR:
        parts.append("The notebook pins its version, so it runs for a student exactly as written, "
                     "and nothing read from the releases shows the approach it teaches has changed.")
    elif action == "watch" and score.chapter_id is None and market_wants_it(score) is False:
        parts.append("Not a new lesson until more employers ask for it.")

    parts.append(f"{confirmed} confirmed, {unverified} unverified, priority {score.priority:.2f}.")

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


def assess_trend(trend: Trend, chapter: dict | None, published: dict) -> dict:
    confirmed = [claim for claim in trend.claims if claim.verdict == "confirmed"]
    has_chapter = chapter is not None
    chapter = chapter or {}
    legacy = [marker for marker in chapter.get("legacy_api", [])
              if marker["package"] == trend.subject]

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


def run(run_dir: Path) -> None:
    trends = runio.load_artifact(run_dir, "trends", Trend)
    scores = runio.load_artifact(run_dir, "scores", Score)
    signals = runio.load_artifact(run_dir, "signals", Signal)
    chapters = load_chapters()

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

        chapter = chapters.get(score.chapter_id)
        assessment = assess_trend(trend, chapter, published)
        action = decide_action(score, assessment)

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
                rationale=written or build_rationale(trend, score, action, assessment, chapter),
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
