import re
from datetime import datetime, timezone
from pathlib import Path
import json

from src import changes, feasibility, gap, memory, runio
from src.adapters import model
from src.agents import evidence
from src.agents import judge as judge_agent
from src.agents import placement
from src.reading import judge_educational_value
from src.schema import MarketSignal, PackageFacts, Score, Signal, Trend

# How much a change matters. How ready the course is to teach it, maturity,
# prerequisites and difficulty, is scored apart as feasibility: folded in here,
# an easy version pin outranked a real change and every threshold moved at once.
WEIGHTS = {
    "relevance": 0.25,
    "impact": 0.25,
    "educational_value": 0.25,
    "market_relevance": 0.25,
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


def installs(chapter: dict, subject: str) -> bool:
    return subject in chapter.get("pins", {}) or subject in chapter.get("installs_unpinned", [])


def match_chapter(trend: Trend, chapters: list[dict]) -> str | None:
    subject_words = word_set(trend.subject)
    primary = primary_name(trend.subject)

    named_candidates = [c for c in chapters if primary in chapter_vocabulary(c)]

    # A chapter that names the package AND installs it beats one that only mentions
    # it in passing: C2 says "OpenAI API key setup", but C5 is where openai is used.
    preferred = [c for c in named_candidates if installs(c, trend.subject)] or named_candidates

    best_chapter_id = None
    best_named = 0

    for chapter in preferred:
        named = len(subject_words & chapter_vocabulary(chapter))

        if named > best_named:
            best_named = named
            best_chapter_id = chapter["chapter_id"]

    if best_chapter_id is not None:
        return best_chapter_id

    # Nothing names it, but a chapter's own notebooks install it. That chapter owns
    # it, even when it is a dependency the course never talks about.
    installing = [c["chapter_id"] for c in chapters if installs(c, trend.subject)]

    if installing:
        return installing[0]

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

# Job posts over the last three months, and downloads last month, each turned
# into a 1 to 5 step. The steps were set against real numbers from the hiring
# threads (fastapi 24, langchain 17, crewai 4) and pypistats (fastapi 363M,
# langgraph 44M, crewai 6.5M), not picked in the abstract.
JOB_STEPS = [(20, 5), (10, 4), (5, 3), (1, 2)]
DOWNLOAD_STEPS = [(50_000_000, 5), (10_000_000, 4), (1_000_000, 3), (100_000, 2)]

# Employers asking by name is the question a bootcamp is asking; downloads are
# inflated by CI and by everything that depends on a package without anyone
# learning it. Jobs lead, downloads temper.
JOB_WEIGHT = 0.6


def step(value: int, steps: list[tuple[int, int]]) -> int:
    for floor, score in steps:
        if value >= floor:
            return score

    return 1


def market_score(signal: MarketSignal | None) -> tuple[int, str]:
    """Whether the market wants this tool, and whether we actually measured it."""
    jobs = step(signal.jobs, JOB_STEPS) if signal and signal.jobs is not None else None
    downloads = step(signal.downloads, DOWNLOAD_STEPS) if signal and signal.downloads is not None else None

    if jobs is None and downloads is None:
        return 2, "default"

    if jobs is None:
        return downloads, "measured"

    if downloads is None:
        return jobs, "measured"

    return round(JOB_WEIGHT * jobs + (1 - JOB_WEIGHT) * downloads), "measured"


def what_changed(trend: Trend, signals: list[Signal]) -> dict:
    """Everything this trend's official releases say they changed.

    Only GitHub releases carry notes; a PyPI record says a version exists and
    nothing about what is in it.
    """
    notes = [signal.body for signal in signals
             if signal.id in trend.signal_ids and signal.tier == 1 and signal.body]

    if not notes:
        return {}

    return changes.combine([changes.classify(body) for body in notes])


def impact_of(trend: Trend, summary: dict) -> tuple[int, str]:
    """How much the releases changed, on a 1 to 5 scale.

    This used to be the number of signals, which rewarded a package for how
    often it shipped: ten alphas of chores outscored one release that changed a
    concept. It now reads what the releases actually say.
    """
    if not summary:
        return 2, "default"

    impact = changes.weight(summary)
    versions = [claim.version for claim in trend.claims if claim.version]

    if versions and all(changes.is_prerelease(version) for version in versions):
        impact = max(1, impact - 1)

    return impact, "measured"


def judge_input(trend: Trend, summary: dict) -> list[str]:
    """What the judge is shown. A version number alone told it nothing, so every
    package came back as a minor update worth 2 out of 5."""
    if summary.get("highlights"):
        return summary["highlights"]

    if summary:
        return [f"only maintenance: {summary.get('fix', 0)} fixes and "
                f"{summary.get('noise', 0)} chores, no new features or breaking changes"]

    return [claim.text for claim in trend.claims]


def edits_by_package(chapters: list[dict]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}

    for chapter in chapters:
        for edit in chapter.get("material_edits", []):
            found.setdefault(edit["package"], []).append(edit)

    return found


def score_trend(
    trend: Trend,
    chapters: list[dict],
    signals: list[Signal],
    market: dict[str, MarketSignal] | None = None,
    facts: dict[str, dict] | None = None,
    as_of: datetime | None = None,
    taught: set[str] | None = None,
    tools: dict | None = None,
    place=None,
) -> Score:
    chapter_id = match_chapter(trend, chapters)
    placed_by_agent = None

    if chapter_id is None and place is not None:
        # The rules place a trend by overlap, and say nothing when there is none. That
        # silence is often right, so only a chapter whose own words carry the name is
        # taken: anything weaker establishes an order, not an owner, and is left out.
        proposed = place(trend, chapters)

        if proposed and proposed["relation"] == "owns":
            chapter_id, placed_by_agent = proposed["chapter"], proposed

    subject_in_curriculum = any(
        trend.subject.lower() in topic.lower()
        for chapter in chapters
        for topic in chapter["topics_covered"]
    )

    summary = what_changed(trend, signals)
    demand = (market or {}).get(trend.subject)

    chapter_title = next(
        (c["title"] for c in chapters if c["chapter_id"] == chapter_id),
        None,
    )
    # The agent looks before it scores: it may read this run's releases, search the
    # course for the names that moved, and read the demand already counted. What it
    # cites is checked against the tool output before any of it is kept, and when it
    # has nothing left the old single question answers instead.
    claims_seen = judge_input(trend, summary)
    judged_by_agent = judge_agent.judge(trend.subject, claims_seen, chapter_title, tools or {})
    judgement = judged_by_agent or judge_educational_value(trend.subject, claims_seen, chapter_title)

    impact, impact_source = impact_of(trend, summary)
    market_relevance, market_source = market_score(demand)

    package = (facts or {}).get(trend.subject)
    newest = gap.newest([claim.version for claim in trend.claims if claim.verdict == "confirmed"])
    mature, mature_source, mature_detail = feasibility.maturity(package, as_of or datetime.now(timezone.utc),
                                                                summary, newest)
    ready, ready_source, ready_detail = feasibility.prerequisites(
        trend.subject, package, taught if taught is not None else feasibility.taught_packages(chapters))
    effort, effort_source, effort_detail = feasibility.difficulty(
        chapter_id, summary, edits_by_package(chapters).get(trend.subject, []), mature)

    dimensions = {
        "relevance": 5 if subject_in_curriculum else 2,
        "impact": impact,
        "educational_value": judgement["value"] if judgement else 3,
        "market_relevance": market_relevance,
        "maturity": mature,
        "prerequisites": ready,
        "difficulty": effort,
    }

    provenance = {
        "chapter": "agent" if placed_by_agent else ("matched" if chapter_id else "none"),
        "relevance": "measured",
        "impact": impact_source,
        "educational_value": "agent" if judged_by_agent else ("judged" if judgement else "default"),
        "market_relevance": market_source,
        "maturity": mature_source,
        "prerequisites": ready_source,
        "difficulty": effort_source,
    }

    factors = {"maturity": mature_detail, "prerequisites": ready_detail, "difficulty": effort_detail}

    if placed_by_agent:
        # A chapter nothing matched travels with the line that put it there.
        factors["chapter"] = {"why": placed_by_agent["why"], "quote": placed_by_agent["quote"],
                              "looked": placed_by_agent["looked"]}
    if judged_by_agent:
        # What the agent read travels with the score, so the number can be opened.
        factors["educational_value"] = {
            "reason": judged_by_agent["reason"],
            "cites": judged_by_agent["cites"],
            "dropped": judged_by_agent["dropped"],
            "looked": judged_by_agent["looked"],
        }

    return Score(
        trend_id=trend.id,
        chapter_id=chapter_id,
        confidence=average_confidence(trend),
        dimensions=dimensions,
        provenance=provenance,
        priority=calculate_priority(dimensions),
        changes=summary,
        market=demand.model_dump() if demand else {},
        feasibility=feasibility.score(dimensions),
        factors=factors,
    )


def load_chapters() -> list[dict]:
    path = Path("fixtures/curriculum.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["chapters"]


def run(run_dir: Path) -> None:
    signals = runio.load_artifact(run_dir, "signals", Signal)
    trends = runio.load_artifact(run_dir, "trends", Trend)
    chapters = load_chapters()

    # A run collected before market data existed has no market artifact. Its
    # scores come out as unmeasured on that dimension rather than failing.
    market_path = run_dir / "market.json"
    market_rows = ([entry.model_dump() for entry in runio.load_artifact(run_dir, "market", MarketSignal)]
                   if market_path.exists() else [])
    market = {row["subject"]: MarketSignal(**row) for row in market_rows}

    # The same goes for package histories: without them maturity and
    # prerequisites fall back to default, and say so.
    packages_path = run_dir / "packages.json"
    facts = ({entry.subject: entry.model_dump() for entry in runio.load_artifact(run_dir, "packages", PackageFacts)}
             if packages_path.exists() else {})

    # Maturity is measured at the moment the run collected, so a replay next
    # month judges the same age it judged on the day.
    as_of = memory.run_started(run_dir.name) or datetime.now(timezone.utc)
    taught = feasibility.taught_packages(chapters)

    # The agent's tools read this run's own artifacts and the course on disk, so a
    # replay without keys simply finds no model, and the rules answer as they always did.
    tools = evidence.tools_for(run_dir, market_rows) if model.available() else {}
    place = placer(chapters) if model.available() else None

    scores = [
        score_trend(trend, chapters, signals, market, facts, as_of, taught, tools, place)
        for trend in trends
    ]

    homeless = sum(1 for score in scores if not score.chapter_id)
    found = sum(1 for score in scores if score.provenance.get("chapter") == "agent")

    if place is not None:
        print(f"placed: {found} chapters an agent found, {homeless} trends the course has no chapter for")

    runio.save_artifact(run_dir, "scores", scores)


def placer(chapters: list[dict]):
    """Ask where a trend belongs, with the tools already built once for the whole run."""
    kit = placement.tools_for(chapters, course_uses=evidence.course_uses_tool())

    def place(trend: Trend, _chapters: list[dict]):
        about = " ".join(claim.text for claim in trend.claims[:4])
        return placement.place(trend.subject, about, chapters, kit)

    return place