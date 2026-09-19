import re
from pathlib import Path
import json

from src import runio
from src.schema import Score, Signal, Trend

WEIGHTS = {
    "relevance": 0.25,
    "impact": 0.25,
    "educational_value": 0.20,
    "difficulty": 0.10,
    "market_relevance": 0.20,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

STOP_WORDS = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
    "into", "from", "by", "at", "as", "is", "was", "were", "be", "it", "its",
    "this", "that", "these", "those", "new", "using", "use", "build",
    "building", "release", "released", "version", "first", "basic", "simple",
}


def word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def chapter_vocabulary(chapter: dict) -> set[str]:
    text = " ".join(chapter["topics_covered"] + chapter.get("tools_covered", []))
    return word_set(text)


def primary_name(subject: str) -> str:
    return subject.replace("_", "-").split("-")[0]


def match_chapter(trend: Trend, chapters: list[dict]) -> str | None:
    subject_words = word_set(trend.subject)
    primary = primary_name(trend.subject)

    best_chapter_id = None
    best_named = 0

    for chapter in chapters:
        chapter_words = chapter_vocabulary(chapter)

        if primary not in chapter_words:
            continue

        named = len(subject_words & chapter_words)

        if named > best_named:
            best_named = named
            best_chapter_id = chapter["chapter_id"]

    if best_chapter_id is not None:
        return best_chapter_id

    trend_text = " ".join([trend.subject] + [claim.text for claim in trend.claims])
    trend_words = word_set(trend_text) - STOP_WORDS

    best_overlap = 0

    for chapter in chapters:
        chapter_words = chapter_vocabulary(chapter) - STOP_WORDS
        overlap = len(trend_words & chapter_words)

        if overlap > best_overlap:
            best_overlap = overlap
            best_chapter_id = chapter["chapter_id"]

    if best_overlap >= 3:
        return best_chapter_id

    return None


def calculate_priority(dimensions: dict[str, int]) -> float:
    return sum(
        dimensions[name] * weight
        for name, weight in WEIGHTS.items()
    )

def average_confidence(trend: Trend) -> float:
    if not trend.claims:
        return 0.0

    return sum(claim.confidence for claim in trend.claims) / len(trend.claims)

def score_trend(
    trend: Trend,
    chapters: list[dict],
    signals: list[Signal],
) -> Score:
    chapter_id = match_chapter(trend, chapters)

    subject_in_curriculum = any(
        trend.subject.lower() in topic.lower()
        for chapter in chapters
        for topic in chapter["topics_covered"]
    )

    tier2_count = sum(
        signal.tier == 2
        for signal in signals
        if signal.id in trend.signal_ids
    )

    dimensions = {
        "relevance": 5 if subject_in_curriculum else 2,
        "impact": 2 + min(3, len(trend.signal_ids)),
        "educational_value": 3,
        "difficulty": 2,
        "market_relevance": 2 + min(3, tier2_count),
    }

    provenance = {
        "relevance": "measured",
        "impact": "measured",
        "educational_value": "default",
        "difficulty": "default",
        "market_relevance": "measured",
    }

    return Score(
        trend_id=trend.id,
        chapter_id=chapter_id,
        confidence=average_confidence(trend),
        dimensions=dimensions,
        provenance=provenance,
        priority=calculate_priority(dimensions),
    )


def load_chapters() -> list[dict]:
    path = Path("fixtures/curriculum.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["chapters"]


def run(run_dir: Path) -> None:
    signals = runio.load_artifact(run_dir, "signals", Signal)
    trends = runio.load_artifact(run_dir, "trends", Trend)
    chapters = load_chapters()

    scores = [
        score_trend(trend, chapters, signals)
        for trend in trends
    ]

    runio.save_artifact(run_dir, "scores", scores)