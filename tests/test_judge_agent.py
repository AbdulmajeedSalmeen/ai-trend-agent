"""The judge agent: it must look before it scores, and cite what it actually saw.

Every model answer here is scripted and every tool is local, so these tests call
nothing. What they pin down is the part that makes the agent safe to trust: a citation
that the tool output does not support is dropped, and a score left with no surviving
citation is no score at all, which sends the caller back to the rules.
"""

import json

from src.agents import evidence, judge


def scripted(*answers):
    """A model that says these things in order, and records what it was asked."""
    said = list(answers)
    asked = []

    def ask(system, user):
        asked.append(user)
        return said.pop(0) if said else None

    ask.asked = asked
    return ask


def tools():
    return {
        "course_uses": lambda symbol="": f"{symbol} appears in 2 notebooks: intro.ipynb cell 7; chat.ipynb cell 12",
        "demand": lambda subject="": f"{subject}: 20 job posts in 3 months, 4000 installs",
        "release_notes": lambda package="": f"{package} 1.4.2: AgentExecutor moved to langchain-classic",
    }


def test_it_looks_before_it_answers():
    ask = scripted(
        {"tool": "course_uses", "args": {"symbol": "AgentExecutor"}},
        {"answer": {"educational_value": 5, "reason": "the course teaches the name that moved",
                    "cites": [{"factor": "the course uses it", "tool": "course_uses",
                               "quote": "intro.ipynb cell 7"}]}},
    )
    verdict = judge.judge("langchain", ["AgentExecutor moved"], "Week 3 - LangChain", tools(), ask=ask)

    assert verdict["value"] == 5
    assert verdict["cites"][0]["tool"] == "course_uses"
    assert verdict["dropped"] == 0
    assert [step["tool"] for step in verdict["looked"]] == ["course_uses"]
    # the second turn has to carry what the first one found, or the loop is decoration
    assert "intro.ipynb cell 7" in ask.asked[1]


def test_a_citation_the_tools_never_returned_is_dropped():
    ask = scripted(
        {"tool": "demand", "args": {"subject": "langchain"}},
        {"answer": {"educational_value": 4, "reason": "invented support",
                    "cites": [{"factor": "demand", "tool": "demand", "quote": "900 job posts"},
                              {"factor": "demand", "tool": "demand", "quote": "20 job posts"}]}},
    )
    verdict = judge.judge("langchain", ["something changed"], None, tools(), ask=ask)

    assert verdict["dropped"] == 1
    assert [c["quote"] for c in verdict["cites"]] == ["20 job posts"]


def test_a_tool_named_with_its_brackets_on_is_the_same_tool():
    ask = scripted(
        {"tool": "demand", "args": {"subject": "langchain"}},
        {"answer": {"educational_value": 3, "reason": "what the market asks for",
                    "cites": [{"factor": "demand", "tool": "demand()", "quote": "20 job posts"}]}},
    )
    verdict = judge.judge("langchain", ["x"], None, tools(), ask=ask)

    assert verdict["dropped"] == 0 and verdict["cites"][0]["tool"] == "demand"


def test_a_score_with_nothing_left_under_it_is_not_a_score():
    ask = scripted({"answer": {"educational_value": 5, "reason": "trust me",
                               "cites": [{"factor": "demand", "tool": "demand", "quote": "600 job posts"}]}})
    assert judge.judge("langchain", ["something changed"], None, tools(), ask=ask) is None


def test_a_score_outside_the_scale_is_refused():
    ask = scripted({"answer": {"educational_value": 9, "reason": "off the scale", "cites": []}})
    assert judge.judge("langchain", ["x"], None, tools(), ask=ask) is None


def test_it_cannot_loop_forever():
    ask = scripted(*[{"tool": "demand", "args": {"subject": "langchain"}} for _ in range(10)])
    assert judge.judge("langchain", ["x"], None, tools(), ask=ask, max_steps=3) is None
    assert len(ask.asked) == 4


def test_an_invented_tool_is_answered_and_not_run():
    ask = scripted(
        {"tool": "ask_the_internet", "args": {"q": "anything"}},
        {"answer": {"educational_value": 2, "reason": "fell back to what it could see",
                    "cites": [{"factor": "demand", "tool": "demand", "quote": "20 job posts"}]}},
    )
    called = []
    kit = tools()
    kit["demand"] = lambda subject="": called.append(subject) or "langchain: 20 job posts in 3 months"
    verdict = judge.judge("langchain", ["x"], None, kit, ask=ask)

    assert verdict is None or verdict["value"] == 2
    assert "no such tool" in ask.asked[1]
    assert called == []


def test_no_model_means_no_judgement():
    assert judge.judge("langchain", ["x"], None, tools(), ask=lambda system, user: None) is None
    assert judge.judge("langchain", ["x"], None, {}, ask=scripted({"answer": {}})) is None


def test_the_tools_read_the_run_and_the_course(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "raw" / "github_0.json").write_text(json.dumps({
        "repo": "langchain-ai/langchain",
        "releases": [{"name": "langchain==1.4.2", "body": "AgentExecutor moved to langchain-classic"}],
    }), encoding="utf-8")
    week = tmp_path / "notebooks" / "week 3"
    week.mkdir(parents=True)
    (week / "intro.ipynb").write_text(json.dumps({
        "cells": [{"cell_type": "markdown", "source": "intro"},
                  {"cell_type": "code", "source": "from langchain.agents import AgentExecutor"}],
    }), encoding="utf-8")

    kit = evidence.tools_for(run_dir, [{"subject": "langchain", "jobs": 20, "downloads": 4000, "months": 3}],
                             notebook_dir=tmp_path / "notebooks")

    assert "AgentExecutor moved" in kit["release_notes"](package="langchain")
    assert "intro.ipynb cell 2" in kit["course_uses"](symbol="AgentExecutor")
    assert "no notebook uses" in kit["course_uses"](symbol="NoSuchName")
    assert "20 job posts" in kit["demand"](subject="langchain")
    assert "nothing counted" in kit["demand"](subject="unknown-package")


def test_a_reply_that_is_not_an_object_ends_it_without_a_crash():
    for reply in (["4"], "4", 7):
        assert judge.judge("langchain", ["AgentExecutor moved"], "Week 3 - LangChain", tools(),
                           ask=scripted(reply)) is None


def test_fields_of_the_wrong_type_are_refused_not_crashed_on():
    good = {"factor": "the course uses it", "tool": "course_uses", "quote": "intro.ipynb cell 7"}

    def verdict(**fields):
        ask = scripted({"tool": "course_uses", "args": {"symbol": "AgentExecutor"}},
                       {"answer": {"educational_value": 4, **fields}})
        return judge.judge("langchain", ["AgentExecutor moved"], "Week 3 - LangChain", tools(), ask=ask)

    assert verdict(cites=3) is None
    assert verdict(cites="course_uses") is None
    assert verdict(reason=5, cites=[good])["reason"] == ""
    assert verdict(reason=["kept"], cites=[good])["value"] == 4


def test_a_line_the_model_wrote_into_its_own_call_is_not_evidence():
    ask = scripted(
        {"tool": "demand", "args": {"subject": "crewai is required in 900 job posts"}},
        {"answer": {"educational_value": 5, "reason": "demand",
                    "cites": [{"factor": "demand", "tool": "demand", "quote": "crewai is required in 900 job posts"}]}})
    assert judge.judge("crewai", ["crewai shipped flows"], None, tools(), ask=ask) is None


def test_the_loop_s_own_words_and_one_letter_are_not_evidence():
    empty = {**tools(), "release_notes": lambda package="": ""}
    for quote in ("nothing found", "no such tool", "n"):
        ask = scripted({"tool": "release_notes", "args": {"package": "langchain"}},
                       {"tool": "nonsense", "args": {}},
                       {"answer": {"educational_value": 4, "reason": "x",
                                   "cites": [{"factor": "f", "tool": "release_notes", "quote": quote},
                                             {"factor": "f", "tool": "nonsense", "quote": quote}]}})
        assert judge.judge("langchain", ["something changed"], None, empty, ask=ask) is None


def test_a_line_from_an_earlier_call_to_the_same_tool_still_counts():
    ask = scripted(
        {"tool": "course_uses", "args": {"symbol": "AgentExecutor"}},
        {"tool": "course_uses", "args": {"symbol": "ToolNode"}},
        {"answer": {"educational_value": 5, "reason": "the course uses both",
                    "cites": [{"factor": "reach", "tool": "course_uses",
                               "quote": "agentexecutor appears in 2 notebooks"}]}})
    verdict = judge.judge("langchain", ["AgentExecutor moved"], "Week 3 - LangChain", tools(), ask=ask)
    assert verdict is not None and verdict["dropped"] == 0
