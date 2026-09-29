"""The material judge: it must look before it weighs, and cite what it actually saw.

Severity is not worth. The rules could only read a status, so a helper that moved and a
credential a student will copy came out identical, and every entry carried the word
"medium" for effort because the driver wrote it once. This is what asks the question,
and these hold it to the same bargain the package judge lives by: a citation the tools
never returned is dropped, and a score with none left is no score, which sends the
caller back to the rules.

Every model answer is scripted and every tool is local, so nothing here calls out.
"""

import pytest

from src.agents import worth


def entry(status="superseded", technique="ReAct agent"):
    return {
        "id": "week3/Demo", "title": "Demo_LangChain_Intro", "week": "week 3",
        "teaches": [{"technique": technique, "as_taught": "builds a ReAct agent", "cell": 3}],
        "findings": [{"technique": technique, "status": status, "now": "create_react_agent",
                      "instead": "create_agent", "why1": "the constructor moved in 1.0"}],
    }


def scripted(*answers):
    said, asked = list(answers), []

    def ask(system, user):
        asked.append(user)
        return said.pop(0) if said else None

    ask.asked = asked
    return ask


def tools():
    return worth.tools_for(
        findings=lambda **_: "ReAct agent is superseded: the constructor moved in 1.0",
        course_uses=lambda term: f"{term} appears in 6 notebooks: intro.ipynb cell 7; chat.ipynb cell 12",
        papers=lambda term: f"41 papers named {term} in 30 days")


def answer(score=4, effort="large", cites=None):
    return {"answer": {"worth": score, "effort": effort,
                       "reason": "six notebooks teach it, so this is a decision about the course",
                       "cites": cites if cites is not None else
                       [{"factor": "how far it reaches", "tool": "course_uses",
                         "quote": "appears in 6 notebooks"}]}}


def test_it_looks_before_it_weighs():
    ask = scripted({"tool": "course_uses", "args": {"term": "ReAct agent"}}, answer())

    weighed = worth.judge(entry(), tools(), ask=ask)

    assert weighed["worth"] == 4 and weighed["effort"] == "large" and weighed["dropped"] == 0
    assert weighed["cites"][0]["tool"] == "course_uses"
    assert [step["tool"] for step in weighed["looked"]] == ["course_uses"]
    # the answering turn has to carry what the first one found, or the loop is decoration
    assert "6 notebooks" in ask.asked[1]


def test_a_citation_the_tools_never_returned_is_dropped():
    ask = scripted({"tool": "course_uses", "args": {"term": "ReAct agent"}},
                   answer(cites=[{"factor": "reach", "tool": "course_uses", "quote": "appears in 40 notebooks"},
                                 {"factor": "reach", "tool": "course_uses", "quote": "appears in 6 notebooks"}]))

    weighed = worth.judge(entry(), tools(), ask=ask)

    assert weighed["dropped"] == 1
    assert [cite["quote"] for cite in weighed["cites"]] == ["appears in 6 notebooks"]


def test_a_tool_named_with_its_brackets_on_is_the_same_tool():
    ask = scripted({"tool": "course_uses", "args": {"term": "ReAct agent"}},
                   answer(cites=[{"factor": "reach", "tool": "course_uses()",
                                  "quote": "appears in 6 notebooks"}]))

    weighed = worth.judge(entry(), tools(), ask=ask)

    assert weighed["dropped"] == 0 and weighed["cites"][0]["tool"] == "course_uses"


def test_a_citation_credited_to_the_wrong_tool_is_dropped():
    ask = scripted({"tool": "course_uses", "args": {"term": "ReAct agent"}},
                   answer(cites=[{"factor": "reach", "tool": "papers", "quote": "appears in 6 notebooks"}]))

    assert worth.judge(entry(), tools(), ask=ask) is None


def test_a_score_with_nothing_left_under_it_is_not_a_score():
    ask = scripted(answer(cites=[{"factor": "reach", "tool": "course_uses", "quote": "appears in 6 notebooks"}]))
    assert worth.judge(entry(), tools(), ask=ask) is None

    ask = scripted({"tool": "findings", "args": {}}, answer(cites=[]))
    assert worth.judge(entry(), tools(), ask=ask) is None


@pytest.mark.parametrize("bad", [{"worth": 9}, {"worth": 0}, {"worth": "high"}, {"worth": None},
                                 {"effort": "enormous"}, {"effort": ""}])
def test_a_score_or_an_effort_off_the_scale_is_refused(bad):
    proposal = answer()
    proposal["answer"].update(bad)
    ask = scripted({"tool": "findings", "args": {}}, proposal)

    assert worth.judge(entry(), tools(), ask=ask) is None


def test_a_notebook_where_nothing_moved_is_never_asked():
    ask = scripted(answer())
    assert worth.judge(entry(status="current"), tools(), ask=ask) is None
    assert ask.asked == []


def test_it_cannot_look_forever_and_is_told_when_it_is_out_of_turns():
    ask = scripted(*[{"tool": "papers", "args": {"term": "agents"}} for _ in range(9)])

    assert worth.judge(entry(), tools(), ask=ask, max_steps=2) is None
    assert len(ask.asked) == 3
    assert "2 tool calls left" in ask.asked[0]
    assert "no tool calls left. Answer now" in ask.asked[-1]


def test_an_invented_tool_is_answered_and_not_run():
    called = []
    kit = tools()
    kit["course_uses"] = lambda **kwargs: called.append(kwargs) or "appears in 6 notebooks"
    ask = scripted({"tool": "ask_the_internet", "args": {"q": "anything"}}, answer())

    weighed = worth.judge(entry(), kit, ask=ask)

    assert weighed is None or weighed["worth"] == 4
    assert "no such tool" in ask.asked[1]
    assert called == []


def test_calling_the_same_thing_twice_is_answered_without_calling_it():
    calls = []
    kit = tools()
    kit["papers"] = lambda **kwargs: calls.append(kwargs) or "41 papers"
    ask = scripted({"tool": "papers", "args": {"term": "x"}}, {"tool": "papers", "args": {"term": "x"}},
                   answer(cites=[{"factor": "the field", "tool": "papers", "quote": "41 papers"}]))

    worth.judge(entry(), kit, ask=ask)

    assert len(calls) == 1
    assert "you already called this" in ask.asked[2]


def test_the_tools_pass_the_name_through_whatever_it_is_called():
    kit = worth.tools_for(findings=lambda **_: "what the reviewer said",
                          course_uses=lambda term: f"saw {term}", papers=lambda term: f"read {term}")

    assert kit["findings"]() == "what the reviewer said"
    assert kit["course_uses"](term="MCP") == "saw MCP"
    assert kit["course_uses"](symbol="MCP") == "saw MCP"
    assert kit["papers"](name="MCP") == "read MCP"

    bare = worth.tools_for(findings=lambda **_: "x")
    assert "not searched" in bare["course_uses"](term="MCP")
    assert "not checked" in bare["papers"](term="MCP")


def test_no_model_means_the_rules_decide():
    assert worth.judge(entry(), tools(), ask=lambda system, user: None) is None


@pytest.mark.parametrize("reply", [["4"], "4", 7])
def test_a_reply_that_is_not_an_object_ends_it_without_a_crash(reply):
    assert worth.judge(entry(), tools(), ask=scripted(reply)) is None


@pytest.mark.parametrize("cites", [3, "course_uses"])
def test_citations_that_are_not_a_list_are_refused_not_crashed_on(cites):
    ask = scripted({"tool": "course_uses", "args": {"term": "ReAct agent"}}, answer(cites=cites))
    assert worth.judge(entry(), tools(), ask=ask) is None
