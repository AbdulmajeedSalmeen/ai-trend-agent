"""Which failures drop a provider, and which are just a bad answer.

A run on 2026-09-29 made 237 model calls and 136 of them failed. One key was out of
credit, which is a dead key and correctly ended it. The rest were answers we could not
parse: the provider replied, over a working key, with prose where JSON was asked for.
Two of those in a row dropped each provider, and eighty-one calls after that were
skipped without ever being tried. Everything downstream fell back to rules.

These hold the difference. A provider that cannot be reached is dropped after two
tries, because the third will not go better. A provider that answers with something
unreadable is given longer, because it is working.

Nothing here touches the network: _call is replaced by a function that says what
happened.
"""

import pytest

from src.adapters import model


@pytest.fixture(autouse=True)
def two_providers(monkeypatch):
    monkeypatch.setattr(model, "config", lambda: {"on": True})
    monkeypatch.setattr(model, "_configured", lambda: [
        {"provider": "first", "base_url": "x", "model": "m", "key": "k"},
        {"provider": "second", "base_url": "y", "model": "n", "key": "j"},
    ])
    model.reset()
    yield
    model.reset()


def answering(script):
    """A _call that returns whatever the script says for the provider it is asked about."""
    asked = []

    def call(settings, system, user, max_tokens, timeout, action):
        asked.append(settings["provider"])
        return script(settings["provider"], asked.count(settings["provider"]))

    call.asked = asked
    return call


def unreadable():
    return (None, None, False, True)


def unreachable():
    return (None, None, False, False)


def fine():
    return ({"ok": True}, None, False, False)


def test_a_provider_that_cannot_be_reached_is_dropped_after_two_tries(monkeypatch):
    monkeypatch.setattr(model, "_call", answering(lambda name, nth: unreachable()))

    for _ in range(3):
        model.ask_json("s", "u", action="probe")

    assert model.halted() is not None
    assert [entry["provider"] for entry in model.providers()] == []


def test_an_answer_we_cannot_read_does_not_drop_a_working_provider(monkeypatch):
    monkeypatch.setattr(model, "_call", answering(lambda name, nth: unreadable()))

    for _ in range(3):
        assert model.ask_json("s", "u", action="probe") is None

    # both are still worth asking: they answered, we just could not read them
    assert [entry["provider"] for entry in model.providers()] == ["first", "second"]
    assert model.halted() is None


def test_a_provider_that_only_ever_answers_unreadably_is_dropped_in_the_end(monkeypatch):
    monkeypatch.setattr(model, "_call", answering(lambda name, nth: unreadable()))

    for _ in range(model.UNREADABLE_STRIKES):
        model.ask_json("s", "u", action="probe")

    assert model.providers() == []
    assert "could not be read" in model.halted()


def test_one_good_answer_wipes_the_slate(monkeypatch):
    # unreadable, unreadable, then fine, then unreadable again: never close to dropped
    script = {1: unreadable, 2: unreadable, 3: fine, 4: unreadable}
    monkeypatch.setattr(model, "_call", answering(lambda name, nth: script.get(nth, fine)()))

    for _ in range(4):
        model.ask_json("s", "u", action="probe")

    assert [entry["provider"] for entry in model.providers()] == ["first", "second"]


def test_a_dead_key_still_ends_that_provider_at_once(monkeypatch):
    def script(name, nth):
        return (None, "HTTP 429 out of credit", False, False) if name == "first" else fine()

    monkeypatch.setattr(model, "_call", answering(script))

    assert model.ask_json("s", "u", action="probe") == {"ok": True}
    assert [entry["provider"] for entry in model.providers()] == ["second"]


def test_an_unreadable_first_provider_lets_the_second_answer(monkeypatch):
    def script(name, nth):
        return unreadable() if name == "first" else fine()

    call = answering(script)
    monkeypatch.setattr(model, "_call", call)

    assert model.ask_json("s", "u", action="probe") == {"ok": True}
    assert call.asked == ["first", "second"]


@pytest.mark.parametrize("text", ['["a", "b"]', "7", '"just a string"'])
def test_json_that_is_not_an_object_is_an_answer_we_cannot_read(text):
    # Every caller asked for one object and reads it with .get; a list or a number
    # handed through crashed the stage that asked.
    with pytest.raises(ValueError):
        model.parse_json(text)


def test_an_object_after_a_sentence_is_still_read():
    assert model.parse_json('Here it is: {"a": 1}') == {"a": 1}


def refusing(code, generation=None):
    """A provider that turns the request down with a 400 and says why, as Groq does."""
    import io
    import json
    import urllib.error

    error = {"message": "Tool choice is none, but model called a tool", "type": "invalid_request_error", "code": code}
    if generation is not None:
        error["failed_generation"] = generation
    body = json.dumps({"error": error}).encode("utf-8")

    def urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    return urlopen


GROQ = {"provider": "groq", "base_url": "https://api.groq.test/v1", "model": "openai/gpt-oss-120b", "key": "k"}


def test_an_answer_sent_as_a_tool_call_is_read_out_of_the_refusal(monkeypatch):
    # gpt-oss on Groq answered placement's first turn through its own tool calling.
    # Groq refused the call (400, tool_use_failed) and handed back what it tried to
    # send, which was the answer. Every placement on 2026-09-29 was lost this way.
    import json

    generation = json.dumps({"name": "tool.exec", "arguments": {"tool": "chapters", "args": {}}})
    monkeypatch.setattr(model.urllib.request, "urlopen", refusing("tool_use_failed", generation))
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)

    answer, fatal, limited, unreadable = model._call(GROQ, "s", "u", 100, 5, "placement_agent")

    assert answer == {"tool": "chapters", "args": {}}
    assert fatal is None and not limited and not unreadable


def test_any_other_refusal_says_its_code_and_is_not_an_answer(monkeypatch):
    from src import trace

    monkeypatch.setattr(model.urllib.request, "urlopen", refusing("context_length_exceeded"))
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(trace, "current", trace.Trace(run_id="run_test", model="groq", budget=1000))

    answer, fatal, limited, unreadable = model._call(GROQ, "s", "u", 100, 5, "placement_agent")

    assert answer is None and fatal is None
    assert any("context_length_exceeded" in step.note for step in trace.current.steps)


@pytest.mark.parametrize("generation, meant", [
    ({"name": "tool.exec", "arguments": {"tool": "chapters", "args": {}}}, {"tool": "chapters", "args": {}}),
    ({"name": "functions.chapter", "arguments": {"id": "C8"}}, {"tool": "chapter", "args": {"id": "C8"}}),
    ({"name": "answer", "arguments": {"answer": {"chapter": "C8"}}}, {"answer": {"chapter": "C8"}}),
    ({"name": "tool.exec", "arguments": '{"sentence": "Update C8."}'}, {"sentence": "Update C8."}),
    ({"name": "tool.exec", "arguments": [1, 2]}, None),
    ("not a call at all", None),
    (None, None),
])
def test_what_a_refused_tool_call_meant(generation, meant):
    import json

    text = generation if generation is None or isinstance(generation, str) else json.dumps(generation)
    assert model.from_tool_call(text) == meant


def test_an_answer_cut_off_at_its_ceiling_is_asked_again_with_room(monkeypatch):
    # A reasoning model bills its thinking against the same ceiling. When it runs out
    # halfway through the object, the reply is not a bad answer, it is a short budget:
    # the same as an empty reply, which already got a second, larger try.
    import io
    import json

    replies = ['{"answer": {"chapter": "C14", "quote": "c14 (week 4): agents for real', 
               '{"answer": {"chapter": "C14", "quote": "c14 (week 4): agents for real-world tasks"}}']
    ceilings = []

    def urlopen(request, timeout=None):
        ceilings.append(json.loads(request.data)["max_tokens"])
        finish = "length" if len(ceilings) == 1 else "stop"
        reply = io.BytesIO(json.dumps({"choices": [{"finish_reason": finish,
                                                    "message": {"content": replies[len(ceilings) - 1]}}],
                                       "usage": {}}).encode("utf-8"))
        reply.headers = {}
        return reply

    monkeypatch.setattr(model.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(model.time, "sleep", lambda seconds: None)

    answer, fatal, limited, unreadable = model._call(GROQ, "s", "u", 500, 5, "placement_agent")

    assert answer == {"answer": {"chapter": "C14", "quote": "c14 (week 4): agents for real-world tasks"}}
    assert ceilings == [500, 2000]
