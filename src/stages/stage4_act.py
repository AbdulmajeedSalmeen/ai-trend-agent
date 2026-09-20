import json
import re
from pathlib import Path

from src import gap, memory, runio
from src.reading import write_recommendation
from src.schema import Recommendation, Score, Signal, Trend

CURRICULUM_PATH = Path("fixtures/curriculum.json")


def decide_action(score: Score, assessment: dict | None = None) -> str:
    if score.confidence < 0.5:
        return "watch"

    if score.chapter_id is None:
        return "add_new_lesson" if score.priority >= 2.5 else "watch"

    if assessment is not None:
        if assessment["kind"] in gap.ACTIONABLE:
            return "update_existing_material"

        if assessment["kind"] != gap.UNKNOWN:
            return "watch"

        if assessment["released_since"] >= 3 and score.priority >= 3.0:
            return "update_existing_material"

        return "watch"

    return "update_existing_material" if score.priority >= 3.0 else "watch"


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
        parts = [assessment["sentence"]]
    else:
        opening = f"Chapter {score.chapter_id} teaches: {chapter['teaches']}" if chapter else ""
        parts = [opening, assessment["sentence"], gap.legacy_sentence(assessment),
                 gap.staleness_sentence(assessment)]

    if action == "watch" and score.confidence < 0.5:
        parts.append("Not acted on: the claims are too weak to trust.")
    elif action == "watch" and assessment["kind"] == gap.PATCH_ONLY:
        parts.append("Nothing to rewrite yet.")

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
