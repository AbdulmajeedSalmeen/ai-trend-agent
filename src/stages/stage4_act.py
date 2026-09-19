from pathlib import Path
from src.schema import Recommendation, Score, Trend
from src import runio

def decide_action(score: Score) -> str:
    if score.confidence < 0.5:
        return "watch"

    if score.chapter_id is not None and score.priority >= 3.0:
        return "update_existing_material"

    if score.chapter_id is None and score.priority >= 2.5:
        return "add_new_lesson"

    return "watch"


def build_rationale(trend: Trend, score: Score, action: str) -> str:
    confirmed = 0
    unverified = 0
    for claim in trend.claims:
        if claim.verdict == "confirmed":
            confirmed += 1
        else:
            unverified += 1
        
    if score.chapter_id is None:
        chapter = "no matching chapter"
    else:
        chapter = f"chapter {score.chapter_id}"

    if action == "watch" and score.confidence < 0.5:
        note = " Not acted on: evidence too weak."
    else:
        note = ""
      

    return f"{trend.subject}: {confirmed} confirmed, {unverified} unverified. Priority {score.priority:.2f}, Confidence {score.confidence:.2f}, {chapter}.{note}"


def run(run_dir: Path) -> None:
    trends = runio.load_artifact(run_dir, "trends", Trend)
    scores = runio.load_artifact(run_dir, "scores", Score)

    scores_by_trend = {}

    for score in scores:
        scores_by_trend[score.trend_id] = score

    recommendations = []
    skipped = 0
    for trend in trends:
        score = scores_by_trend.get(trend.id)

        if score is None:
            skipped += 1
            continue

        action = decide_action(score)
        recommendation = Recommendation(
            trend_id=trend.id,
            action=action,
            chapter_id=score.chapter_id,
            rationale=build_rationale(trend, score, action),
        )

        recommendations.append(recommendation)   

    runio.save_artifact(run_dir, "recommendations", recommendations)

    print(f"{len(recommendations)} recommendations, {skipped} trends skipped")

