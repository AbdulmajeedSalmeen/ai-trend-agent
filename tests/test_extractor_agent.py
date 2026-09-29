"""The extractor: it may fill in a version, and only one it could point at.

A claim with no version is unverifiable, so filling one in is the single most
dangerous thing any agent here does: it turns something nobody checked into something
the page calls confirmed. These tests hold the three rules that stop it. The version
must be a release this run collected, the release must predate the post, and the line
tying them together must be in what a tool returned.

Every model answer is scripted and every signal is local, so nothing here calls out.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.agents import extractor
from src.schema import Claim, Signal
from src.stages import stage2b_verify

DAY = datetime(2026, 9, 21, tzinfo=timezone.utc)


def release(version="1.2.12", days=0, notes="create_react_agent moved to langchain-classic",
            source="github", ident=None):
    return Signal(id=ident or f"gh_{version}_{days}", source=source, tier=1, subject="langgraph",
                  title=f"langgraph=={version}", url=f"https://github.com/x/releases/{version}",
                  published_at=DAY + timedelta(days=days), body=notes)


def post(days=1, title="The new langgraph release broke my agent"):
    return Signal(id="hn_1", source="hackernews", tier=2, subject=None, title=title,
                  url="https://news.ycombinator.com/item?id=1", published_at=DAY + timedelta(days=days),
                  body="the react agent constructor is gone and nothing says where it went")


def claim():
    return Claim(text="The new langgraph release broke my agent", subject="langgraph",
                 version=None, source_signal_id="hn_1")


def scripted(*answers):
    said, asked = list(answers), []

    def ask(system, user):
        asked.append(user)
        return said.pop(0) if said else None

    ask.asked = asked
    return ask


def answer(version="1.2.12", quote="create_react_agent moved to langchain-classic"):
    return {"answer": {"version": version, "quote": quote, "why": "the post describes exactly that move"}}


def test_it_reads_before_it_names_a_version():
    signals = [release(), post()]
    ask = scripted({"tool": "notes", "args": {"version": "1.2.12"}}, answer())

    found = extractor.extract(claim(), post(), signals, ask=ask)

    assert found["version"] == "1.2.12"
    assert found["evidence_url"] == "https://github.com/x/releases/1.2.12"
    assert [step["tool"] for step in found["looked"]] == ["notes"]
    # the answering turn must carry what it read, or the loop is decoration
    assert "langchain-classic" in ask.asked[1]


def test_a_version_this_run_never_collected_is_refused():
    signals = [release(), post()]
    ask = scripted({"tool": "notes", "args": {"version": "1.2.12"}}, answer(version="0.9.9"))

    assert extractor.extract(claim(), post(), signals, ask=ask) is None


def test_a_release_the_post_predates_is_refused():
    # the release lands ten days after the post, so the post cannot be reporting it
    signals = [release(days=10), post(days=0)]
    ask = scripted({"tool": "releases", "args": {}}, answer())

    assert extractor.extract(claim(), post(days=0), signals, ask=ask) is None


def test_a_quote_no_tool_returned_is_refused():
    signals = [release(), post()]
    ask = scripted({"tool": "releases", "args": {}},
                   answer(quote="the maintainers announced this on their blog in June"))

    assert extractor.extract(claim(), post(), signals, ask=ask) is None


@pytest.mark.parametrize("said", [None, "1.2.12 or maybe 1.2.11", ""])
def test_saying_it_cannot_tell_is_an_answer(said):
    signals = [release(), post()]
    ask = scripted(answer(version=said))

    assert extractor.extract(claim(), post(), signals, ask=ask) is None


def test_answering_null_ends_it_instead_of_spending_the_rest_of_the_budget():
    signals = [release(), post()]
    ask = scripted({"tool": "releases", "args": {}}, {"answer": None}, answer())

    assert extractor.extract(claim(), post(), signals, ask=ask) is None
    assert len(ask.asked) == 2


def test_it_cannot_look_forever():
    signals = [release(), post()]
    ask = scripted(*[{"tool": "releases", "args": {}} for _ in range(9)])

    assert extractor.extract(claim(), post(), signals, ask=ask, max_steps=2) is None
    assert len(ask.asked) == 3


def test_with_no_releases_collected_it_never_asks():
    ask = scripted(answer())
    assert extractor.extract(claim(), post(), [post()], ask=ask) is None
    assert ask.asked == []


def test_one_release_per_version_newest_first_and_the_copy_with_notes_wins():
    signals = [release(version="1.2.11", days=-3),
               release(version="1.2.12", days=0, notes="", source="pypi", ident="pypi_a"),
               release(version="1.2.12", days=0, notes="the real notes", ident="gh_a"),
               post()]
    found = extractor.candidates("langgraph", signals)

    assert [row["version"] for row in found] == ["1.2.12", "1.2.11"]
    assert found[0]["notes"] == "the real notes"
    assert extractor.candidates("something-else", signals) == []


def test_the_tools_hand_over_the_post_the_list_and_one_set_of_notes():
    releases = extractor.candidates("langgraph", [release(), release(version="1.2.11", days=-3), post()])
    tools = extractor.tools_for(post(), releases)

    assert "2026-09-22" in tools["post"]() and "broke my agent" in tools["post"]()
    assert "1.2.12 on 2026-09-21" in tools["releases"]() and "1.2.11 on 2026-09-18" in tools["releases"]()
    assert "langchain-classic" in tools["notes"](version="1.2.12")
    assert "no release 3.0" in tools["notes"](version="3.0")
    assert "collected no releases" in extractor.tools_for(post(), [])["releases"]()


def test_a_version_worked_out_is_confirmed_for_less_than_one_stated():
    signals = [release(), post()]
    tiers = {"hn_1": 2, signals[0].id: 1}
    ask = scripted({"tool": "notes", "args": {"version": "1.2.12"}}, answer())

    worked_out = stage2b_verify.verify_claim(
        claim(), signals, tiers, extract=lambda c, p, s: extractor.extract(c, p, s, ask=ask))
    assert worked_out.verdict == "confirmed"
    assert worked_out.evidence_kind == "cross_source"
    assert worked_out.version_source == "extracted"
    assert worked_out.confidence == 0.75

    stated = stage2b_verify.verify_claim(claim().model_copy(update={"version": "1.2.12"}), signals, tiers)
    assert stated.confidence == 0.9 and stated.version_source == "stated"


def test_without_an_extractor_nothing_changes():
    signals = [release(), post()]
    unfilled = stage2b_verify.verify_claim(claim(), signals, {"hn_1": 2})

    assert unfilled.verdict == "unverified" and unfilled.version is None
    assert unfilled.version_source is None


def test_a_claim_whose_post_is_gone_is_left_alone():
    orphan = claim().model_copy(update={"source_signal_id": "hn_missing"})
    called = []

    left = stage2b_verify.verify_claim(orphan, [release()], {}, extract=lambda *a: called.append(a))
    assert left.version is None and called == []
