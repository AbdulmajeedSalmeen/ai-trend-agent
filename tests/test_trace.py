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


def only(provider="openai", model_name="gpt-4o-mini"):
    return [{"base_url": "https://example.test/v1", "model": model_name,
             "key": "test", "provider": provider}]


def use(monkeypatch, entries):
    """conftest turns the model off for every test. These tests are about the
    adapter itself, so they turn it back on for their own fake providers."""
    from src.adapters import model

    monkeypatch.setattr(model, "_configured", lambda: entries)
    monkeypatch.setattr(model, "config", lambda: entries[0] if entries else None)


def refusal(code, body=b"", headers=None):
    import io
    import urllib.error

    return urllib.error.HTTPError(
        "https://example.test", code, "refused", headers or {}, io.BytesIO(body)
    )


def test_a_spent_account_drops_that_provider_for_the_rest_of_the_run(monkeypatch):
    from src.adapters import model

    model.reset()
    use(monkeypatch, only())

    calls = []

    def refuse(*args, **kwargs):
        calls.append(1)
        raise refusal(429, b'{"error": {"code": "project_spend_limit_exceeded"}}')

    monkeypatch.setattr(model.urllib.request, "urlopen", refuse)
    trace.start("run_halt", "openai:gpt-4o-mini")

    assert model.ask_json("s", "u", action="read_post") is None
    assert model.ask_json("s", "u", action="read_post") is None
    assert model.ask_json("s", "u", action="read_post") is None

    assert len(calls) == 1
    assert model.halted() == "HTTP 429 out of credit"
    model.reset()


def test_a_rate_limit_waits_and_tries_the_same_provider_again(monkeypatch):
    import io
    import json as jsonlib

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("groq", "openai/gpt-oss-120b"))
    slept = []
    monkeypatch.setattr(model.time, "sleep", lambda seconds: slept.append(seconds))

    calls = []

    def answer(request, timeout=None):
        calls.append(1)

        if len(calls) == 1:
            raise refusal(429, b'{"error": {"message": "rate limit reached for requests"}}',
                          {"Retry-After": "7"})

        payload = {"choices": [{"message": {"content": '{"ok": 1}'}, "finish_reason": "stop"}],
                   "usage": {}}
        return _as_context(io.BytesIO(jsonlib.dumps(payload).encode()))

    monkeypatch.setattr(model.urllib.request, "urlopen", answer)
    trace.start("run_rate", "groq")

    assert model.ask_json("s", "u", action="read_post") == {"ok": 1}
    assert slept == [7.0]
    assert model.halted() is None
    assert "rate limited" in trace.current.steps[0].note
    model.reset()


def test_an_ambiguous_rate_limit_waits_rather_than_ending_the_run(monkeypatch):
    from src.adapters import model

    model.reset()
    use(monkeypatch, only("groq", "openai/gpt-oss-120b"))
    slept = []
    monkeypatch.setattr(model.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(model.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(refusal(429, b"too many requests")))
    trace.start("run_rate_2", "groq")

    assert model.ask_json("s", "u", action="read_post") is None
    assert slept == [5.0]
    model.reset()


def test_a_timeout_is_still_worth_retrying(monkeypatch):
    from src.adapters import model

    model.reset()
    use(monkeypatch, only())
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
    model.reset()


def test_a_refused_key_hands_over_to_the_next_provider(monkeypatch):
    import io
    import json as jsonlib
    import urllib.error

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("openai") + only("groq", "llama-3.3-70b-versatile"))

    seen = []

    def answer(request, timeout=None):
        body = jsonlib.loads(request.data)
        seen.append(body["model"])

        if body["model"] == "gpt-4o-mini":
            raise urllib.error.HTTPError("https://example.test", 401, "bad key", {}, None)

        payload = {"choices": [{"message": {"content": '{"ok": 1}'}}],
                   "usage": {"prompt_tokens": 11, "completion_tokens": 3}}
        return io.BytesIO(jsonlib.dumps(payload).encode())

    monkeypatch.setattr(model.urllib.request, "urlopen",
                        lambda request, timeout=None: _as_context(answer(request, timeout)))
    trace.start("run_failover", "openai, groq")

    assert model.ask_json("s", "u", action="read_post") == {"ok": 1}
    assert seen == ["gpt-4o-mini", "llama-3.3-70b-versatile"]

    # the dead provider is not asked again, the working one is
    assert model.ask_json("s", "u", action="read_post") == {"ok": 1}
    assert seen == ["gpt-4o-mini", "llama-3.3-70b-versatile", "llama-3.3-70b-versatile"]

    assert model.halted() is None
    assert trace.current.steps[-1].action == "read_post@groq"
    assert trace.current.tokens == 28
    model.reset()


def test_every_provider_down_is_reported_as_halted(monkeypatch):
    import urllib.error

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("openai") + only("groq"))

    def refuse(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.test", 401, "bad key", {}, None)

    monkeypatch.setattr(model.urllib.request, "urlopen", refuse)
    trace.start("run_all_down", "openai, groq")

    assert model.ask_json("s", "u", action="read_post") is None
    assert model.halted() == "HTTP 401"
    model.reset()


class _as_context:
    def __init__(self, stream):
        self.stream = stream

    def __enter__(self):
        return self.stream

    def __exit__(self, *args):
        return False


def test_a_provider_that_keeps_timing_out_is_dropped_too(monkeypatch):
    from src.adapters import model

    model.reset()
    use(monkeypatch, only("nvidia", "slow-model"))
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)

    calls = []

    def slow(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("too slow")

    monkeypatch.setattr(model.urllib.request, "urlopen", slow)
    trace.start("run_strikes", "nvidia:slow-model")

    assert model.ask_json("s", "u", action="read_post") is None
    assert model.halted() is None

    assert model.ask_json("s", "u", action="read_post") is None
    assert model.halted() == "2 failed calls running"

    before = len(calls)
    assert model.ask_json("s", "u", action="read_post") is None
    assert len(calls) == before
    model.reset()


def test_one_good_answer_clears_the_strikes(monkeypatch):
    import io
    import json as jsonlib

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("groq", "llama-3.3-70b-versatile"))
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)

    attempts = {"n": 0}

    def flaky(request, timeout=None):
        attempts["n"] += 1

        if attempts["n"] <= 2:
            raise TimeoutError("too slow")

        payload = {"choices": [{"message": {"content": '{"ok": 1}'}}], "usage": {}}
        return _as_context(io.BytesIO(jsonlib.dumps(payload).encode()))

    monkeypatch.setattr(model.urllib.request, "urlopen", flaky)
    trace.start("run_flaky", "groq")

    # the first ask spends both of its own attempts on timeouts and takes a strike
    assert model.ask_json("s", "u", action="read_post") is None
    assert model._strikes["groq"] == 1

    assert model.ask_json("s", "u", action="read_post") == {"ok": 1}
    assert model._strikes["groq"] == 0
    assert model.halted() is None
    model.reset()


def test_a_slow_provider_does_not_block_the_one_behind_it(monkeypatch):
    import io
    import json as jsonlib

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("nvidia", "slow-model") + only("groq", "llama-3.3-70b-versatile"))
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)

    seen = []

    def answer(request, timeout=None):
        body = jsonlib.loads(request.data)
        seen.append(body["model"])

        if body["model"] == "slow-model":
            raise TimeoutError("too slow")

        payload = {"choices": [{"message": {"content": '{"ok": 1}'}}], "usage": {}}
        return _as_context(io.BytesIO(jsonlib.dumps(payload).encode()))

    monkeypatch.setattr(model.urllib.request, "urlopen", answer)
    trace.start("run_slow_first", "nvidia, groq")

    assert model.ask_json("s", "u", action="read_post") == {"ok": 1}
    assert seen == ["slow-model", "slow-model", "llama-3.3-70b-versatile"]
    model.reset()


def test_every_request_names_us_because_a_cdn_refuses_anonymous_clients(monkeypatch):
    import io
    import json as jsonlib

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("groq", "openai/gpt-oss-120b"))
    sent = {}

    def capture(request, timeout=None):
        sent.update(request.headers)
        payload = {"choices": [{"message": {"content": '{"ok": 1}'}}], "usage": {}}
        return _as_context(io.BytesIO(jsonlib.dumps(payload).encode()))

    monkeypatch.setattr(model.urllib.request, "urlopen", capture)
    trace.start("run_ua", "groq")

    assert model.ask_json("s", "u", action="read_post") == {"ok": 1}
    assert sent.get("User-agent", "").startswith("ai-trend-agent/")
    model.reset()


def test_a_model_with_no_published_price_says_so_rather_than_reporting_zero():
    record = trace.Trace(model="groq:openai/gpt-oss-120b")
    record.record("x", 1.0, tokens_in=1000, tokens_out=200)

    summary = record.summary()

    assert summary["priced"] is False
    assert summary["tokens"] == 1200


def test_a_reasoning_model_that_spent_its_budget_gets_more_room(monkeypatch):
    import io
    import json as jsonlib

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("groq", "openai/gpt-oss-120b"))
    budgets = []

    def answer(request, timeout=None):
        budgets.append(jsonlib.loads(request.data)["max_tokens"])

        if len(budgets) == 1:
            payload = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                       "usage": {"prompt_tokens": 91, "completion_tokens": 20}}
        else:
            payload = {"choices": [{"message": {"content": '{"ok": 1}'}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 91, "completion_tokens": 30}}

        return _as_context(io.BytesIO(jsonlib.dumps(payload).encode()))

    monkeypatch.setattr(model.urllib.request, "urlopen", answer)
    trace.start("run_reasoning", "groq")

    assert model.ask_json("s", "u", max_tokens=200, action="read_post") == {"ok": 1}
    assert budgets == [200, 800]
    assert trace.current.steps[0].note == "spent its budget reasoning"
    model.reset()


def test_model_order_is_also_a_guest_list(monkeypatch):
    from src.adapters import model

    monkeypatch.setenv("OPENAI_API_KEY", "a")
    monkeypatch.setenv("GROQ_API_KEY", "b")
    monkeypatch.setenv("NVIDIA_API_KEY", "c")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    monkeypatch.setenv("MODEL_ORDER", "groq,openai")
    assert [entry["provider"] for entry in model._configured()] == ["groq", "openai"]

    monkeypatch.setenv("MODEL_ORDER", "groq")
    assert [entry["provider"] for entry in model._configured()] == ["groq"]

    monkeypatch.delenv("MODEL_ORDER")
    assert [entry["provider"] for entry in model._configured()] == ["openai", "groq", "nvidia"]


def test_a_rate_limit_that_mentions_billing_is_still_only_a_rate_limit(monkeypatch):
    import io
    import json as jsonlib

    from src.adapters import model

    model.reset()
    use(monkeypatch, only("groq", "openai/gpt-oss-120b"))
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)
    calls = []

    def answer(request, timeout=None):
        calls.append(1)

        if len(calls) == 1:
            raise refusal(429, b'{"error": {"code": "rate_limit_exceeded", "message": '
                               b'"Rate limit reached. Upgrade at console.groq.com/settings/billing"}}')

        payload = {"choices": [{"message": {"content": '{"ok": 1}'}, "finish_reason": "stop"}],
                   "usage": {}}
        return _as_context(io.BytesIO(jsonlib.dumps(payload).encode()))

    monkeypatch.setattr(model.urllib.request, "urlopen", answer)
    trace.start("run_rate_billing", "groq")

    assert model.ask_json("s", "u", action="read_post") == {"ok": 1}
    assert model.halted() is None


def test_a_spent_account_is_still_terminal(monkeypatch):
    from src.adapters import model

    model.reset()
    use(monkeypatch, only())
    monkeypatch.setattr(model.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            refusal(429, b'{"error": {"code": "insufficient_quota"}}')))
    trace.start("run_spent", "openai")

    assert model.ask_json("s", "u", action="read_post") is None
    assert model.halted() == "HTTP 429 out of credit"
    model.reset()
