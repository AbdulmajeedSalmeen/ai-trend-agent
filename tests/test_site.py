from datetime import datetime, timezone

from src import runio
from src.schema import Claim, Recommendation, Score, Signal, Trend
from web.site import build_payload


def build_run(path, rationale_ar=None, **recalled):
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
        **recalled,
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


def test_a_standing_ask_says_when_it_began_not_only_how_many_runs(tmp_path):
    run_dir = tmp_path / "run_20260921T104824Z"
    run_dir.mkdir()
    build_run(run_dir, runs_flagged=9, first_seen_run="run_20260920T080135Z")

    item = build_payload(run_dir)["items"][0]

    assert item["runs_flagged"] == 9
    assert item["asked_since"] == "2026-09-20"
    assert item["asked_days"] == 1


def test_a_first_ask_has_no_start_date(tmp_path):
    run_dir = tmp_path / "run_20260921T104824Z"
    run_dir.mkdir()
    build_run(run_dir, first_seen_run="run_20260921T104824Z")

    item = build_payload(run_dir)["items"][0]

    assert item["asked_since"] is None
    assert item["asked_days"] is None


def test_payload_survives_a_run_without_recommendations(tmp_path):
    runio.save_artifact(tmp_path, "signals", [])

    payload = build_payload(tmp_path)

    assert payload["items"] == []
    assert payload["counts"]["signals"] == 0


def test_the_concepts_the_course_does_not_teach_arrive_with_their_reason_in_both_languages(tmp_path):
    build_run(tmp_path)

    concepts = build_payload(tmp_path)["concepts"]

    assert concepts, "the curriculum file carries at least one concept"
    for concept in concepts:
        assert concept["why"] and concept["why_ar"]
        assert concept["action"] in {"add_new_lesson", "add_optional_content", "watch"}
        assert [evidence["what"] for evidence in concept["evidence"]] == ["added", "absent"]


def test_concepts_are_counted_apart_from_packages(tmp_path):
    build_run(tmp_path)

    payload = build_payload(tmp_path)
    counts = payload["counts"]

    assert counts["concepts"] == len(payload["concepts"])
    assert counts["concept_lessons"] == sum(1 for c in payload["concepts"] if c["action"] == "add_new_lesson")
    assert counts["new_lesson"] == sum(1 for i in payload["items"] if i["action"] == "add_new_lesson")


def test_each_card_carries_its_feasibility_factors_in_both_languages(tmp_path):
    build_run(tmp_path)
    score = Score(trend_id="trend_001", chapter_id="C19", confidence=0.7, priority=3.4,
                  dimensions={"relevance": 5, "maturity": 5, "prerequisites": 5, "difficulty": 1},
                  provenance={"relevance": "measured", "maturity": "measured", "prerequisites": "measured",
                              "difficulty": "measured"},
                  feasibility=4.7,
                  factors={"maturity": {"first_release": "2023-08-01", "age_years": 3.1, "latest_stable": "1.2.11",
                                        "major": 1, "steady": True},
                           "prerequisites": {"basis": "taught"},
                           "difficulty": {"new_material": False, "edit_lines": 0, "chapters": 0, "breaking": 0,
                                          "deprecation": 0}})
    runio.save_artifact(tmp_path, "scores", [score])

    payload = build_payload(tmp_path)
    item = payload["items"][0]

    assert item["feasibility"] == 4.7
    assert set(item["factors"]) == {"maturity", "prerequisites", "difficulty"}
    assert all(factor["why"] and factor["why_ar"] for factor in item["factors"].values())
    assert payload["scoring"]["priority"]["relevance"] == 0.25
