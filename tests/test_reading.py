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
