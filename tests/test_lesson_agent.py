"""The lesson agent: it may propose a lesson, and only one the findings asked for.

A proposed lesson is work somebody has to do, so the expensive failure is not a bad
lesson, it is a plausible one about something nobody found wanting or something the
course already runs. These tests hold the three rules that stop both.

Every model answer is scripted and every tool is local, so nothing here calls out.
"""

import json

import pytest

from src import lessons
from src.agents import lesson


def entry(status="superseded", technique="ReAct agent"):
    return {
        "id": "week3/Demo", "title": "Demo_LangChain_Intro", "week": "week 3",
        "notebook": "notebooks/week 3/Demo_LangChain_Intro.ipynb",
        "teaches": [{"technique": technique, "as_taught": "builds a ReAct agent with AgentExecutor",
                     "quote": "create_react_agent", "cell": 3, "located": True}],
        "findings": [{"technique": technique, "status": status, "now": "create_react_agent",
                      "instead": "create_agent", "why1": "the constructor moved in 1.0",
                      "confidence": "high", "evidence": [], "basis": "read_and_judged"}],
    }


def scripted(*answers):
    said, asked = list(answers), []

    def ask(system, user):
        asked.append(user)
        return said.pop(0) if said else None

    ask.asked = asked
    return ask


def tools():
    return lesson.tools_for(entry(),
                            course_uses=lambda term: f"no notebook uses {term}",
                            papers=lambda term: f"41 papers named {term} in 30 days")


def answer(term="checkpointed agents", answers=("ReAct agent",), covers=None, title=None):
    return {"answer": {
        "title": title or f"Building an agent loop with {term}",
        "term": term,
        "why": "The course teaches a constructor that no longer exists, and never teaches the loop under it.",
        "covers": list(covers or [f"Rebuild the week 3 agent with {term}",
                                  "Interrupt a run and resume it from its last state",
                                  "Compare the two loops on the same task"]),
        "answers": list(answers),
    }}


def test_it_reads_the_findings_then_writes_the_lesson():
    ask = scripted({"tool": "findings", "args": {}}, answer())

    written = lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0)

    assert written["title"].startswith("Building an agent loop")
    assert written["answers"] == ["ReAct agent"] and written["already_in"] == 0
    assert [step["tool"] for step in written["looked"]] == ["findings"]
    # the answering turn must carry what it read, or the loop is decoration
    assert "the constructor moved in 1.0" in ask.asked[1]


def test_it_names_the_findings_in_its_own_words_and_keeps_the_reviewer_spelling():
    ask = scripted(answer(answers=["ReAct agent is superseded", "ReAct agent"]))
    written = lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0)

    assert written["answers"] == ["ReAct agent"]


def test_a_lesson_about_something_nobody_found_wanting_is_refused():
    ask = scripted(answer(answers=["Memory classes"]))
    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0) is None

    ask = scripted(answer(answers=[]))
    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0) is None


def test_a_lesson_the_course_already_runs_is_refused():
    ask = scripted(answer())
    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 3) is None

    ask = scripted(answer())
    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 2)["already_in"] == 2


def test_a_name_the_demand_rules_would_drop_is_dropped_here():
    # not in its own title or covers, so nothing downstream could search for it
    ask = scripted(answer(term="observability", title="Building an agent loop", covers=["a", "b", "c"]))
    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0) is None

    assert lesson.propose(entry(), tools(), ask=scripted(answer(term="")), count=lambda term: 0) is None

    # a word every AI job post carries measures the field, not the lesson
    ask = scripted(answer(term="agents", title="Building agents", covers=["a b", "c d"]))
    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0) is None

    # and a sentence is not a name
    ask = scripted(answer(term="checkpointed agent loops with resume"))
    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0) is None

    # the rule is the one src/lessons.py applies, not a second opinion about names
    written = lesson.propose(entry(), tools(), ask=scripted(answer()), count=lambda term: 0)
    assert lessons.valid(written["term"], {"title": written["title"], "covers": written["covers"]})


@pytest.mark.parametrize("bad", [{"covers": ["only one"]}, {"title": ""}, {"why": ""}])
def test_half_a_lesson_is_not_a_lesson(bad):
    proposal = answer()
    proposal["answer"].update(bad)
    assert lesson.propose(entry(), tools(), ask=scripted(proposal), count=lambda term: 0) is None


def test_a_notebook_whose_lessons_still_hold_is_never_asked():
    ask = scripted(answer())
    assert lesson.propose(entry(status="current"), tools(), ask=ask, count=lambda term: 0) is None
    assert ask.asked == []


def test_a_proposal_is_told_what_was_wrong_and_gets_one_rewrite():
    # first answer names a term its own title does not contain, which nothing could search for
    wrong = answer(term="fine-tuned transformer models", title="BERT for sentiment analysis",
                   covers=["Fine-tune a model", "Compare the two"])
    ask = scripted(wrong, answer())

    written = lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0)

    assert written["term"] == "checkpointed agents"
    complaint = ask.asked[1]
    assert "was thrown away" in complaint
    assert "fine-tuned transformer models" in complaint and "BERT for sentiment analysis" in complaint


def test_a_rewrite_that_breaks_the_same_rule_is_still_thrown_away():
    wrong = answer(term="fine-tuned transformer models", title="BERT for sentiment analysis",
                   covers=["Fine-tune a model", "Compare the two"])
    ask = scripted(wrong, wrong)

    assert lesson.propose(entry(), tools(), ask=ask, count=lambda term: 0) is None
    assert len(ask.asked) == 2


def test_the_complaint_says_which_rule_broke():
    said = lesson.faults(lesson.read_proposal(answer(answers=["Memory classes"])["answer"], entry()),
                         count=lambda term: 0)
    assert "None of your answers matches a finding" in said[0]
    # a complaint that does not say what to choose from gets the same answer back
    assert '"ReAct agent"' in said[0]

    said = lesson.faults(lesson.read_proposal(answer()["answer"], entry()), count=lambda term: 7)
    assert "already teaches" in said[0] and "7" in said[0]

    assert lesson.faults(lesson.read_proposal(answer()["answer"], entry()), count=lambda term: 0) == []


def test_it_cannot_look_forever():
    ask = scripted(*[{"tool": "papers", "args": {"term": "agents"}} for _ in range(9)])
    assert lesson.propose(entry(), tools(), ask=ask, max_steps=2, count=lambda term: 0) is None
    assert len(ask.asked) == 3


def test_saying_the_findings_do_not_add_up_to_a_lesson_is_an_answer():
    assert lesson.propose(entry(), tools(), ask=scripted({"answer": None}), count=lambda term: 0) is None


def test_the_findings_tool_hands_over_what_the_reviewer_said():
    said = lesson.findings_tool(entry())()

    assert "ReAct agent (cell 3)" in said and "is superseded" in said
    assert "Instead: create_agent" in said
    assert "found nothing" in lesson.findings_tool({})()


def test_the_other_tools_pass_the_name_through_whatever_it_is_called():
    kit = lesson.tools_for(entry(), course_uses=lambda term: f"saw {term}", papers=lambda term: f"read {term}")

    assert kit["course_uses"](term="MCP") == "saw MCP"
    assert kit["course_uses"](symbol="MCP") == "saw MCP"
    assert kit["papers"](name="MCP") == "read MCP"
    assert "not searched" in lesson.tools_for(entry())["course_uses"](term="MCP")
    assert "not checked" in lesson.tools_for(entry())["papers"](term="MCP")


def test_the_course_is_counted_here_and_case_does_not_hide_it(tmp_path):
    week = tmp_path / "week 1"
    week.mkdir(parents=True)
    (week / "a.ipynb").write_text(json.dumps({"cells": [{"source": "Evaluation Harness demo"}]}), encoding="utf-8")
    (week / "b.ipynb").write_text(json.dumps({"cells": [{"source": "an evaluation harness"}]}), encoding="utf-8")

    assert lesson.taught_in("evaluation harness", tmp_path) == 2
    assert lesson.taught_in("MCP", tmp_path) == 0
    assert lesson.taught_in("ha", tmp_path) == 0


@pytest.mark.parametrize("reply", [["x"], "x", 7])
def test_a_reply_that_is_not_an_object_ends_it_without_a_crash(reply):
    assert lesson.propose(entry(), tools(), ask=scripted(reply), count=lambda term: 0) is None
