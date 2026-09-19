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