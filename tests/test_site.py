from datetime import datetime, timezone

from src import runio
from src.schema import Claim, Recommendation, Score, Signal, Trend
from web.site import build_payload


def build_run(path, rationale_ar=None):
    signal = Signal(
        id="gh_langgraph_1.2.11",
        source="github",
        tier=1,
        subject="langgraph",
        title="langgraph 1.2.11",
        url="https://github.com/langchain-ai/langgraph/releases/tag/1.2.11",
        published_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )
    claim = Claim(
        text="langgraph version 1.2.11 was released",
        subject="langgraph",
        version="1.2.11",
        verdict="confirmed",
        evidence_url=signal.url,
        confidence=0.7,
        source_signal_id=signal.id,
        evidence_kind="primary_report",
    )
    trend = Trend(id="trend_001", subject="langgraph", signal_ids=[signal.id], claims=[claim])
    score = Score(
        trend_id=trend.id,
        chapter_id="C19",
        confidence=0.7,
        dimensions={"relevance": 5},
        provenance={"relevance": "measured"},
        priority=3.4,
    )
    rec = Recommendation(
        trend_id=trend.id,
        action="update_existing_material",
        chapter_id="C19",
        rationale="langgraph: 1 confirmed, 0 unverified.",
        rationale_ar=rationale_ar,
    )
    runio.save_artifact(path, "signals", [signal])
    runio.save_artifact(path, "trends", [trend])
    runio.save_artifact(path, "scores", [score])
    runio.save_artifact(path, "recommendations", [rec])


def test_payload_joins_trend_score_and_recommendation(tmp_path):
    build_run(tmp_path)

    payload = build_payload(tmp_path)
    item = payload["items"][0]

    assert item["subject"] == "langgraph"
    assert item["action"] == "update_existing_material"
    assert item["chapter_id"] == "C19"
    assert item["claims"][0]["evidence_url"].startswith("https://")
    assert item["claims"][0]["origin_source"] == "github"


def test_payload_counts_evidence_kinds(tmp_path):
    build_run(tmp_path)

    counts = build_payload(tmp_path)["counts"]

    assert counts["kinds"]["primary_report"] == 1
    assert counts["kinds"]["cross_source"] == 0
    assert counts["update"] == 1


def test_payload_carries_the_arabic_reason_beside_the_english(tmp_path):
    build_run(tmp_path, rationale_ar="langgraph: مؤكد 1، غير مؤكد 0.")

    item = build_payload(tmp_path)["items"][0]

    assert item["rationale"] == "langgraph: 1 confirmed, 0 unverified."
    assert item["rationale_ar"] == "langgraph: مؤكد 1، غير مؤكد 0."


def test_a_run_decided_before_the_arabic_existed_says_so_with_none(tmp_path):
    build_run(tmp_path)

    assert build_payload(tmp_path)["items"][0]["rationale_ar"] is None


def test_every_chapter_in_the_payload_says_what_it_teaches_in_both_languages(tmp_path):
    build_run(tmp_path)

    chapters = build_payload(tmp_path)["chapters"]

    assert len(chapters) == 25
    assert all(chapter["teaches"] and chapter["teaches_ar"] for chapter in chapters)


def test_payload_survives_a_run_without_recommendations(tmp_path):
    runio.save_artifact(tmp_path, "signals", [])

    payload = build_payload(tmp_path)

    assert payload["items"] == []
    assert payload["counts"]["signals"] == 0
