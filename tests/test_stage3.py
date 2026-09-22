import json
from pathlib import Path
from datetime import datetime, timezone
from src import runio

import pytest
from src.schema import Claim, Signal, Score, Trend


from src.stages.stage3_score import (
    WEIGHTS,
    calculate_priority,
    match_chapter,
    average_confidence,
    score_trend,
    run,
)

def load_chapters() -> list[dict]:
    path = Path("fixtures/curriculum.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["chapters"]


def test_langgraph_orchestration_matches_c16():
    trend = Trend(
        id="trend_001",
        subject="langgraph",
        signal_ids=[],
        claims=[
            Claim(
                text="LangGraph improves agentic frameworks and orchestration",
                subject="langgraph",
                version="2.0.0",
            )
        ],
    )

    chapter_id = match_chapter(trend, load_chapters())

    assert chapter_id == "C19"

def test_unknown_trend_has_no_chapter():
    trend = Trend(
        id="trend_002",
        subject="novelpackage",
        signal_ids=[],
        claims=[
            Claim(
                text="Novelpackage 1.0.0 was released",
                subject="novelpackage",
                version="1.0.0",
            )
        ],
    )

    chapter_id = match_chapter(trend, load_chapters())

    assert chapter_id is None

def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == 1.0
    
def test_all_fives_have_priority_five():
    dimensions = {
        "relevance": 5,
        "impact": 5,
        "educational_value": 5,
        "difficulty": 5,
        "market_relevance": 5,
    }

    assert calculate_priority(dimensions) == 5.0


def test_all_ones_have_priority_one():
    dimensions = {
        "relevance": 1,
        "impact": 1,
        "educational_value": 1,
        "difficulty": 1,
        "market_relevance": 1,
    }

    assert calculate_priority(dimensions) == 1.0
    
def test_average_confidence_of_confirmed_and_unverified_claims():
    trend = Trend(
        id="trend_003",
        subject="langgraph",
        signal_ids=[],
        claims=[
            Claim(
                text="LangGraph 2.0.0 was released",
                subject="langgraph",
                version="2.0.0",
                confidence=0.9,
            ),
            Claim(
                text="LangGraph 2.1.0 was released",
                subject="langgraph",
                version="2.1.0",
                confidence=0.2,
            ),
        ],
    )

    assert average_confidence(trend) == 0.55
    
def make_signal(signal_id: str, tier: int) -> Signal:
    return Signal(
        id=signal_id,
        source="github" if tier == 1 else "hackernews",
        tier=tier,
        subject="fastapi",
        title="FastAPI update",
        url="https://example.com",
        published_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )


def release(signal_id, body, tier=1, subject="fastapi"):
    return Signal(
        id=signal_id, source="github" if tier == 1 else "hackernews", tier=tier,
        subject=subject, title=f"{subject} release", url=f"https://example.test/{signal_id}",
        published_at=datetime(2026, 9, 19, tzinfo=timezone.utc), body=body,
    )


def fastapi_trend(signal_ids, versions=("1.0.0",)):
    return Trend(
        id="trend_004", subject="fastapi", signal_ids=list(signal_ids),
        claims=[Claim(text=f"fastapi version {v} was released", subject="fastapi",
                      version=v, confidence=0.9) for v in versions],
    )


def test_score_trend_uses_the_v2_rules():
    """v1 scored impact as the number of signals and market relevance as the number
    of Hacker News posts, so a package was rewarded for how often it shipped and
    how much people talked about it. v2 reads what the releases changed and asks
    whether employers hire for it."""
    from src.schema import MarketSignal

    trend = fastapi_trend(["gh_1", "hn_1"])
    signals = [
        release("gh_1", "### Features\n* add streaming responses\n* add typed dependencies\n"
                        "* support lifespan events\n### Bug Fixes\n* fix a header bug"),
        release("hn_1", "", tier=2),
    ]
    market = {"fastapi": MarketSignal(subject="fastapi", jobs=24, downloads=363_000_000)}

    score = score_trend(trend, load_chapters(), signals, market)

    assert score.chapter_id == "C10"
    assert score.dimensions == {
        "relevance": 5,
        "impact": 4,
        "educational_value": 3,
        "market_relevance": 5,
        "maturity": 3,
        "prerequisites": 3,
        "difficulty": 1,
    }
    assert score.provenance["impact"] == "measured"
    assert score.provenance["market_relevance"] == "measured"
    assert score.provenance["maturity"] == "default"
    assert score.priority == 4.25
    assert score.feasibility == round((3 + 3 + 5) / 3, 1)
    assert score.market["jobs"] == 24
    assert score.changes["feature"] == 3


def test_ten_releases_of_chores_score_below_one_real_feature():
    chores = [release(f"gh_{i}", "* chore(deps): bump the minor-and-patch group") for i in range(10)]
    feature = [release("gh_f", "* feat: add durable execution")]

    noisy = score_trend(fastapi_trend([s.id for s in chores]), load_chapters(), chores)
    real = score_trend(fastapi_trend(["gh_f"]), load_chapters(), feature)

    assert noisy.dimensions["impact"] < real.dimensions["impact"]
    assert noisy.dimensions["impact"] == 1


def test_a_breaking_change_has_the_most_impact():
    signals = [release("gh_1", "### BREAKING CHANGES\n* remove the deprecated `Completion` class")]

    score = score_trend(fastapi_trend(["gh_1"]), load_chapters(), signals)

    assert score.dimensions["impact"] == 5


def test_a_run_of_only_prereleases_counts_for_less():
    signals = [release("gh_1", "* feat: add a new router")]

    stable = score_trend(fastapi_trend(["gh_1"], ["1.0.0"]), load_chapters(), signals)
    alpha = score_trend(fastapi_trend(["gh_1"], ["1.1.0a1", "1.1.0a2"]), load_chapters(), signals)

    assert alpha.dimensions["impact"] == stable.dimensions["impact"] - 1


def test_releases_with_no_notes_are_unmeasured_not_low():
    score = score_trend(fastapi_trend(["hn_1"]), load_chapters(), [release("hn_1", "", tier=2)])

    assert score.dimensions["impact"] == 2
    assert score.provenance["impact"] == "default"


def test_no_market_data_is_unmeasured_not_zero():
    score = score_trend(fastapi_trend(["gh_1"]), load_chapters(), [release("gh_1", "* fix: a")])

    assert score.dimensions["market_relevance"] == 2
    assert score.provenance["market_relevance"] == "default"


def test_jobs_lead_and_downloads_temper():
    from src.schema import MarketSignal
    from src.stages.stage3_score import market_score

    widely_installed_rarely_hired = MarketSignal(subject="pandas", jobs=2, downloads=400_000_000)
    hired_for_but_niche = MarketSignal(subject="x", jobs=24, downloads=200_000)

    assert market_score(widely_installed_rarely_hired)[0] < market_score(hired_for_but_niche)[0]


def test_the_judge_is_shown_what_changed_not_the_version(monkeypatch):
    from src.stages import stage3_score

    shown = {}

    def fake_judge(subject, claim_texts, chapter_title):
        shown["texts"] = claim_texts
        return {"value": 4, "reason": "new concept"}

    monkeypatch.setattr(stage3_score, "judge_educational_value", fake_judge)
    signals = [release("gh_1", "* feat: add durable execution\n* chore: bump deps")]

    score_trend(fastapi_trend(["gh_1"]), load_chapters(), signals)

    assert shown["texts"] == ["feature: add durable execution"]


def test_a_maintenance_only_release_tells_the_judge_so(monkeypatch):
    from src.stages import stage3_score

    shown = {}

    def fake_judge(subject, claim_texts, chapter_title):
        shown["texts"] = claim_texts
        return None

    monkeypatch.setattr(stage3_score, "judge_educational_value", fake_judge)
    signals = [release("gh_1", "* fix: a crash\n* chore: bump deps")]

    score_trend(fastapi_trend(["gh_1"]), load_chapters(), signals)

    assert "only maintenance" in shown["texts"][0]


def test_run_writes_scores_json(tmp_path):
    trend = Trend(
        id="trend_005",
        subject="fastapi",
        signal_ids=["gh_1", "hn_1"],
        claims=[
            Claim(
                text="FastAPI application deployment update",
                subject="fastapi",
                version="1.0.0",
                confidence=0.9,
            )
        ],
    )

    signals = [
        make_signal("gh_1", tier=1),
        make_signal("hn_1", tier=2),
    ]

    runio.save_artifact(tmp_path, "signals", signals)
    runio.save_artifact(tmp_path, "trends", [trend])

    run(tmp_path)

    scores = runio.load_artifact(tmp_path, "scores", Score)

    assert len(scores) == 1
    assert scores[0].trend_id == "trend_005"
    assert scores[0].chapter_id == "C10"

def test_sub_package_inherits_the_parent_chapter():
    trend = Trend(
        id="trend_003",
        subject="langgraph-checkpointpostgres",
        signal_ids=[],
        claims=[
            Claim(
                text="langgraph-checkpointpostgres version 3.1.2 was released",
                subject="langgraph-checkpointpostgres",
                version="3.1.2",
            )
        ],
    )

    assert match_chapter(trend, load_chapters()) == "C19"


def test_stop_words_alone_do_not_match_a_chapter():
    trend = Trend(
        id="trend_004",
        subject="novelpackage",
        signal_ids=[],
        claims=[
            Claim(
                text="A deep dive into novelpackage with a new release",
                subject="novelpackage",
                version=None,
            )
        ],
    )

    assert match_chapter(trend, load_chapters()) is None


def test_a_chapter_that_installs_the_package_beats_one_that_only_names_it():
    chapters = [
        {"chapter_id": "C2", "topics_covered": ["OpenAI account and API key setup"],
         "tools_covered": [], "pins": {}, "installs_unpinned": []},
        {"chapter_id": "C5", "topics_covered": ["OpenAI API quickstart", "prompt engineering"],
         "tools_covered": ["openai"], "pins": {}, "installs_unpinned": ["openai"]},
    ]
    trend = Trend(id="t1", subject="openai", signal_ids=["s1"], claims=[])

    assert match_chapter(trend, chapters) == "C5"


def test_a_dependency_no_chapter_talks_about_still_lands_in_the_chapter_that_installs_it():
    chapters = [
        {"chapter_id": "C6", "topics_covered": ["RAG introduction"], "tools_covered": ["FAISS"],
         "pins": {}, "installs_unpinned": []},
        {"chapter_id": "C8", "topics_covered": ["LangChain splitter"], "tools_covered": ["LangChain"],
         "pins": {}, "installs_unpinned": ["pypdf"]},
    ]
    trend = Trend(id="t2", subject="pypdf", signal_ids=["s1"], claims=[])

    assert match_chapter(trend, chapters) == "C8"


def test_a_package_the_course_never_installs_has_no_chapter():
    chapters = [
        {"chapter_id": "C6", "topics_covered": ["RAG introduction"], "tools_covered": ["FAISS"],
         "pins": {}, "installs_unpinned": []},
    ]
    trend = Trend(id="t3", subject="crewai", signal_ids=["s1"], claims=[])

    assert match_chapter(trend, chapters) is None
