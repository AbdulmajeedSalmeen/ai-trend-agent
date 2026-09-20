from datetime import datetime, timezone

from src import reading
from src.schema import Signal


def make_signal(title, body=""):
    return Signal(
        id="hn_1", source="hackernews", tier=2, title=title, body=body,
        url="https://news.ycombinator.com/item?id=1",
        published_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )


def fake_model(monkeypatch, answer):
    monkeypatch.setattr(reading.model, "available", lambda: True)
    monkeypatch.setattr(reading.model, "ask_json", lambda *args, **kwargs: answer)


def test_reading_returns_nothing_without_a_model():
    assert reading.read_claim(make_signal("LangGraph 2.0 is out"), ["langgraph"]) is None


def test_reading_keeps_only_subjects_we_track(monkeypatch):
    fake_model(monkeypatch, {"subject": "some-other-lib", "assertion": "it shipped", "version": "1.0"})

    assert reading.read_claim(make_signal("some-other-lib shipped"), ["langgraph"]) is None


def test_reading_drops_a_post_that_claims_nothing(monkeypatch):
    fake_model(monkeypatch, {"subject": "langgraph", "assertion": "", "version": None})

    assert reading.read_claim(make_signal("Thoughts on LangGraph"), ["langgraph"]) is None


def test_reading_returns_the_claim_it_understood(monkeypatch):
    fake_model(monkeypatch, {"subject": "langgraph", "assertion": "LangGraph added durable execution",
                             "version": "1.2.11"})

    claim = reading.read_claim(make_signal("LangGraph adds durable execution"), ["langgraph"])

    assert claim == {"subject": "langgraph", "assertion": "LangGraph added durable execution", "version": "1.2.11"}


def test_a_judgement_outside_one_to_five_is_refused(monkeypatch):
    fake_model(monkeypatch, {"educational_value": 9, "reason": "very important"})

    assert reading.judge_educational_value("langgraph", ["x"], "C19") is None


def test_a_judgement_inside_the_range_is_kept(monkeypatch):
    fake_model(monkeypatch, {"educational_value": 4, "reason": "students build graphs in week 5"})

    assert reading.judge_educational_value("langgraph", ["x"], "C19")["value"] == 4


def test_a_sentence_that_keeps_the_facts_is_accepted(monkeypatch):
    fake_model(monkeypatch, {"sentence": "The notebooks still call RetrievalQA, gone in 1.4.2."})

    written = reading.write_recommendation(
        "langchain", "update_existing_material", "C8", 3, 1, 4.3,
        must_mention=["1.4.2", "RetrievalQA"],
    )

    assert written == "The notebooks still call RetrievalQA, gone in 1.4.2."


def test_a_sentence_that_drops_the_facts_is_refused(monkeypatch):
    fake_model(monkeypatch, {"sentence": "Update the chapter, there have been several releases."})

    written = reading.write_recommendation(
        "langchain", "update_existing_material", "C8", 3, 1, 4.3,
        must_mention=["1.4.2", "RetrievalQA"],
    )

    assert written is None


def test_a_sentence_that_says_the_opposite_is_refused(monkeypatch):
    fake_model(monkeypatch, {"sentence": "langchain 1.4.2 is out but chapter C8 is up to date."})

    written = reading.write_recommendation(
        "langchain", "update_existing_material", "C8", 3, 1, 4.3, must_mention=["1.4.2"],
    )

    assert written is None


def test_a_negated_contradiction_is_not_a_contradiction():
    assert reading.contradicts_the_verdict("The chapter is not up to date with 1.4.2.") is None


def test_an_asserted_contradiction_is_caught():
    assert reading.contradicts_the_verdict("No action needed for langchain.") == "no action"


def test_a_sentence_with_nothing_to_contradict_passes():
    assert reading.contradicts_the_verdict("The notebooks still call RetrievalQA.") is None


def test_watching_is_allowed_to_say_nothing_needs_doing(monkeypatch):
    fake_model(monkeypatch, {"sentence": "Patch releases only, so the chapter is up to date."})

    written = reading.write_recommendation(
        "langgraph", "watch", "C19", 3, 0, 2.4, must_mention=["1.2.11"] if False else [],
    )

    assert written is not None
