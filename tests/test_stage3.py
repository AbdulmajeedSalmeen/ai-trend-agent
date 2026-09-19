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

    assert chapter_id == "C16"

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


def test_score_trend_uses_the_v1_rules():
    trend = Trend(
        id="trend_004",
        subject="fastapi",
        signal_ids=["gh_1", "hn_1", "hn_2"],
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
        make_signal("hn_2", tier=2),
    ]

    score = score_trend(trend, load_chapters(), signals)

    assert score.chapter_id == "C7"
    assert score.confidence == 0.9
    assert score.dimensions == {
        "relevance": 5,
        "impact": 5,
        "educational_value": 3,
        "difficulty": 2,
        "market_relevance": 4,
    }
    assert score.priority == pytest.approx(4.1)
    
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
    assert scores[0].chapter_id == "C7"