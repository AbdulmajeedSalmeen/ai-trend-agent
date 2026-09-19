from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schema import Claim, Recommendation, Score, Signal, Trend

UTC_NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)


def make_signal(**overrides):
    data = dict(
        id="hn_1",
        source="hackernews",
        tier=2,
        title="LangGraph 2.0 released",
        url="https://news.ycombinator.com/item?id=1",
        published_at=UTC_NOW,
    )
    data.update(overrides)
    return Signal(**data)


def test_valid_signal():
    s = make_signal()
    assert s.tier == 2 and s.subject is None and s.body == ""


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        make_signal(published_at=datetime(2026, 9, 15))


def test_wrong_source_case_rejected():
    with pytest.raises(ValidationError):
        make_signal(source="GitHub")


def test_tier_out_of_range_rejected():
    with pytest.raises(ValidationError):
        make_signal(tier=3)


def test_valid_claim_defaults():
    c = Claim(text="langgraph version 2.0.0 was released", subject="langgraph", version="2.0.0")
    assert c.verdict == "unverified" and c.confidence == 0.2 and c.evidence_url is None


def test_valid_trend_holds_claims():
    c = Claim(text="t", subject="langgraph")
    t = Trend(id="trend_001", subject="langgraph", signal_ids=["hn_1"], claims=[c])
    assert t.claims[0].verdict == "unverified"


def test_valid_score():
    s = Score(
        trend_id="trend_001",
        confidence=0.55,
        dimensions={"relevance": 4},
        provenance={"relevance": "measured"},
        priority=3.35,
    )
    assert s.chapter_id is None


def test_confidence_above_one_rejected():
    with pytest.raises(ValidationError):
        Score(trend_id="x", confidence=2.0, dimensions={}, provenance={}, priority=1.0)


def test_valid_recommendation():
    r = Recommendation(trend_id="trend_001", action="watch", rationale="no confirmed claim yet")
    assert r.chapter_id is None


def test_unknown_action_rejected():
    with pytest.raises(ValidationError):
        Recommendation(trend_id="x", action="delete_curriculum", rationale="r")