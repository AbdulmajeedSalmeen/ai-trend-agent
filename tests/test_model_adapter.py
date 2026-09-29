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
