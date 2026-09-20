import json

from src import trace


def filled(budget=1000, model="openai:gpt-4o-mini"):
    record = trace.Trace(run_id="run_test", model=model, budget=budget)
    record.stage = "cluster"
    record.record("read_post", 120.4, tokens_in=300, tokens_out=40)
    record.record("read_post", 90.0, tokens_in=280, tokens_out=35)
    record.stage = "score"
    record.record("judge_value", 210.0, tokens_in=150, tokens_out=60, ok=False, note="Timeout")
    return record


def test_tokens_are_counted_in_both_directions():
    assert filled().tokens == 300 + 40 + 280 + 35 + 150 + 60


def test_a_failed_call_still_appears_in_the_trace():
    record = filled()

    assert len(record.steps) == 3
    assert record.summary()["failed_calls"] == 1


def test_cost_uses_the_model_price_list():
    record = trace.Trace(model="openai:gpt-4o-mini")
    record.record("x", 1.0, tokens_in=1_000_000, tokens_out=0)

    assert record.cost() == 0.15


def test_an_unknown_model_reports_no_cost_rather_than_a_guess():
    record = trace.Trace(model="someone/else")
    record.record("x", 1.0, tokens_in=1_000_000, tokens_out=1_000_000)

    assert record.cost() == 0.0


def test_the_budget_stops_the_run_when_it_is_spent():
    record = trace.Trace(budget=100)

    assert not record.over_budget()

    record.record("x", 1.0, tokens_in=60, tokens_out=50)

    assert record.over_budget()


def test_work_is_attributed_to_the_stage_that_asked_for_it():
    stages = filled().by_stage()

    assert stages["cluster"]["calls"] == 2
    assert stages["cluster"]["tokens"] == 655
    assert stages["score"]["failed"] == 1


def test_the_summary_reports_the_slowest_call():
    assert filled().summary()["slowest_ms"] == 210.0


def test_a_run_with_no_model_calls_summarises_without_dividing_by_zero():
    summary = trace.Trace(budget=0).summary()

    assert summary["calls"] == 0
    assert summary["slowest_ms"] == 0.0
    assert summary["budget_spent"] == 0.0


def test_the_trace_is_written_beside_the_run(tmp_path):
    filled().save(tmp_path)

    saved = json.loads((tmp_path / "trace.json").read_text(encoding="utf-8"))

    assert saved["summary"]["calls"] == 3
    assert saved["steps"][0]["action"] == "read_post"
    assert saved["steps"][2]["note"] == "Timeout"


def test_starting_a_run_clears_the_previous_one():
    trace.start("run_a", "openai:gpt-4o-mini")
    trace.set_stage("cluster")
    trace.current.record("x", 5.0, tokens_in=10, tokens_out=1)

    trace.start("run_b", "openai:gpt-4o-mini")

    assert trace.current.run_id == "run_b"
    assert trace.current.tokens == 0


def test_the_model_refuses_to_spend_past_the_budget(monkeypatch):
    from src.adapters import model

    monkeypatch.setattr(model, "config", lambda: {
        "base_url": "https://example.test/v1", "model": "gpt-4o-mini",
        "key": "test", "provider": "openai",
    })

    def never_called(*args, **kwargs):
        raise AssertionError("no request may be sent once the budget is spent")

    monkeypatch.setattr(model.urllib.request, "urlopen", never_called)

    trace.start("run_budget", "openai:gpt-4o-mini", budget=10)
    trace.current.record("earlier", 1.0, tokens_in=10, tokens_out=0)

    assert model.ask_json("system", "user", action="read_post") is None
    assert trace.current.steps[-1].note == "budget spent"
    assert trace.current.steps[-1].ok is False


def test_a_spent_quota_stops_the_run_from_asking_again(monkeypatch):
    import urllib.error

    from src.adapters import model

    model.reset()
    monkeypatch.setattr(model, "config", lambda: {
        "base_url": "https://example.test/v1", "model": "gpt-4o-mini",
        "key": "test", "provider": "openai",
    })

    calls = []

    def refuse(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("https://example.test", 429, "quota", {}, None)

    monkeypatch.setattr(model.urllib.request, "urlopen", refuse)
    trace.start("run_halt", "openai:gpt-4o-mini")

    assert model.ask_json("s", "u", action="read_post") is None
    assert model.ask_json("s", "u", action="read_post") is None
    assert model.ask_json("s", "u", action="read_post") is None

    assert len(calls) == 1
    assert model.halted() == "HTTP 429"
    assert trace.current.steps[-1].note == "skipped, HTTP 429"
    model.reset()


def test_a_timeout_is_still_worth_retrying(monkeypatch):
    from src.adapters import model

    model.reset()
    monkeypatch.setattr(model, "config", lambda: {
        "base_url": "https://example.test/v1", "model": "gpt-4o-mini",
        "key": "test", "provider": "openai",
    })
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)

    calls = []

    def slow(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("too slow")

    monkeypatch.setattr(model.urllib.request, "urlopen", slow)
    trace.start("run_timeout", "openai:gpt-4o-mini")

    assert model.ask_json("s", "u", action="read_post") is None
    assert len(calls) == 2
    assert model.halted() is None
