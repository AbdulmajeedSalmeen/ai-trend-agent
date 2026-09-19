from src.schema import Score
from src.stages.stage4_act import decide_action


def make_score(**overrides):
    data = dict(
        trend_id="trend_001",
        chapter_id="C6",
        confidence=0.9,
        dimensions={"relevance": 4},
        provenance={"relevance": "measured"},
        priority=3.2,
    )
    data.update(overrides)
    return Score(**data)


def test_low_confidence_is_watched_even_at_high_priority():
    score = make_score(confidence=0.4, priority=4.0)

    assert decide_action(score) == "watch"


def test_high_priority_with_a_matching_chapter_updates_it():
    score = make_score(priority=3.2, chapter_id="C6")

    assert decide_action(score) == "update_existing_material"


def test_no_matching_chapter_becomes_a_new_lesson():
    score = make_score(priority=2.7, chapter_id=None)

    assert decide_action(score) == "add_new_lesson"


def test_low_priority_is_only_watched():
    score = make_score(priority=2.0, chapter_id="C6")

    assert decide_action(score) == "watch"

from src import gap
from src.stages.stage4_act import build_rationale
from src.schema import Claim, Trend


def make_assessment(kind, released_since=0, pinned="1.4.0", latest="1.4.2"):
    return {
        "subject": "langchain", "pinned": pinned, "latest": latest, "kind": kind,
        "chapter_updated": "2026-08-27", "released_since": released_since,
        "sentence": gap.describe("langchain", pinned, latest, kind), "legacy": [],
    }


def test_patch_releases_alone_never_rewrite_a_chapter():
    score = make_score(priority=4.0, chapter_id="C8")

    assert decide_action(score, make_assessment(gap.PATCH_ONLY)) == "watch"


def test_a_major_release_rewrites_the_chapter():
    score = make_score(priority=3.2, chapter_id="C8")

    assert decide_action(score, make_assessment(gap.BEHIND_MAJOR, pinned="0.1.0")) == "update_existing_material"


def test_a_chapter_already_on_the_newest_version_is_left_alone():
    score = make_score(priority=4.0, chapter_id="C8")

    assert decide_action(score, make_assessment(gap.CURRENT)) == "watch"


def test_an_unrecorded_chapter_version_falls_back_to_how_much_landed_since():
    score = make_score(priority=3.2, chapter_id="C8")
    quiet = make_assessment(gap.UNKNOWN, released_since=1, pinned=None)
    busy = make_assessment(gap.UNKNOWN, released_since=5, pinned=None)

    assert decide_action(score, quiet) == "watch"
    assert decide_action(score, busy) == "update_existing_material"


def test_the_rationale_says_what_the_chapter_teaches_and_what_moved():
    trend = Trend(
        id="trend_007", subject="langchain", signal_ids=["gh_1"],
        claims=[Claim(text="langchain version 1.4.2 was released", subject="langchain",
                      version="1.4.2", verdict="confirmed", confidence=0.9)],
    )
    chapter = {"chapter_id": "C8", "teaches": "Rebuild document QA on LangChain."}
    assessment = make_assessment(gap.BEHIND_MAJOR, released_since=4, pinned="0.1.0")

    rationale = build_rationale(trend, make_score(chapter_id="C8"), "update_existing_material",
                                assessment, chapter)

    assert "Rebuild document QA on LangChain." in rationale
    assert "0.1.0 to 1.4.2" in rationale
    assert "4 of the confirmed releases in this run landed after" in rationale
