"""The reviewer agent: it must read the notebook, and it may only say what is in it.

Every model answer is scripted and every tool is local, so nothing here calls out. What
these pin down is the rule that makes a reviewer's word usable: a quote that is not in
the notebook takes its finding with it, a status the page does not know is dropped, and
a claim that something moved with nothing to read is an opinion, not a finding.
"""

import json

import pytest

from src.agents import reviewer


def notebook(tmp_path):
    week = tmp_path / "week 3"
    week.mkdir(parents=True)
    path = week / "Demo_LangChain_Intro.ipynb"
    path.write_text(json.dumps({"cells": [
        {"cell_type": "markdown", "source": "# Demo: Introduction to LangChain"},
        {"cell_type": "code", "source": "!pip install -q langchain==0.3.*"},
        {"cell_type": "code", "source": "from langchain.agents import create_react_agent, AgentExecutor"},
        {"cell_type": "markdown", "source": "The agent decides which tool to call by reading its own text."},
        {"cell_type": "code", "source": "agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)"},
    ]}), encoding="utf-8")
    return path


def scripted(*answers):
    said, asked = list(answers), []

    def ask(system, user):
        asked.append(user)
        return said.pop(0) if said else None

    ask.asked = asked
    return ask


def tools(cells):
    return {
        "read_cells": reviewer.read_cells_tool(cells),
        "release_notes": lambda package="": f"{package} 1.4.2: create_react_agent moved to langchain-classic",
        "papers": reviewer.papers_tool(lambda term: {"papers": 12, "days": 30,
                                                     "recent": [{"title": "On agents", "published": "2026-09-01"}]}),
    }


def answer(quote, status="superseded", sources=None, technique="ReAct agent"):
    return {"answer": {
        "teaches": [{"technique": technique, "as_taught": "builds a ReAct agent", "quote": quote}],
        "findings": [{"technique": technique, "status": status, "now": "create_react_agent with AgentExecutor",
                      "instead": "create_agent", "why1": "the constructor moved in 1.0", "confidence": "high",
                      "sources": sources if sources is not None else [{"url": "https://docs.example/migrate", "date": "2026-09-01"}]}],
    }}


def test_it_reads_the_notebook_then_answers(tmp_path):
    path = notebook(tmp_path)
    cells = reviewer.cells_of(path)
    ask = scripted({"tool": "read_cells", "args": {"start": 1}},
                   answer("from langchain.agents import create_react_agent"))

    entry = reviewer.review(path, tools(cells), ask=ask)

    assert entry["teaches"][0]["cell"] == 3
    assert entry["findings"][0]["status"] == "superseded"
    assert entry["findings"][0]["basis"] == "read_and_judged"
    assert [s["tool"] for s in entry["looked"]] == ["read_cells"]
    # the answer turn must carry what it read, or the loop is decoration
    assert "create_react_agent" in ask.asked[1]


def test_a_quote_that_is_not_in_the_notebook_is_dropped(tmp_path):
    path = notebook(tmp_path)
    ask = scripted(answer("from langchain.agents import create_openai_functions_agent"))

    assert reviewer.review(path, tools(reviewer.cells_of(path)), ask=ask) is None


def test_a_finding_about_a_technique_it_never_located_is_dropped(tmp_path):
    path = notebook(tmp_path)
    proposal = answer("from langchain.agents import create_react_agent")
    proposal["answer"]["findings"][0]["technique"] = "Memory classes"

    entry = reviewer.review(path, tools(reviewer.cells_of(path)), ask=scripted(proposal))

    assert entry["teaches"] and entry["findings"] == []
    assert entry["dropped"] == 1


def test_a_status_the_page_does_not_know_is_dropped(tmp_path):
    path = notebook(tmp_path)
    entry = reviewer.review(path, tools(reviewer.cells_of(path)),
                            ask=scripted(answer("create_react_agent", status="ancient")))
    assert entry["findings"] == []


def test_a_move_with_nothing_to_read_is_not_a_finding(tmp_path):
    path = notebook(tmp_path)
    entry = reviewer.review(path, tools(reviewer.cells_of(path)),
                            ask=scripted(answer("create_react_agent", sources=[])))
    assert entry["findings"] == []

    still_fine = reviewer.review(path, tools(reviewer.cells_of(path)),
                                 ask=scripted(answer("create_react_agent", status="current", sources=[])))
    assert still_fine["findings"][0]["status"] == "current"


def test_it_cannot_read_forever(tmp_path):
    path = notebook(tmp_path)
    ask = scripted(*[{"tool": "read_cells", "args": {"start": 1}} for _ in range(12)])
    assert reviewer.review(path, tools(reviewer.cells_of(path)), ask=ask, max_steps=3) is None
    assert len(ask.asked) == 4


def test_the_window_tool_hands_over_the_notebook_a_piece_at_a_time(tmp_path):
    cells = reviewer.cells_of(notebook(tmp_path))
    read = reviewer.read_cells_tool(cells, window=2)

    first = read(start=1)
    assert "cells 1 to 2 of 5" in first and "Introduction to LangChain" in first
    assert "no cells from 99" in read(start=99)


def test_a_rephrased_quote_still_locates(tmp_path):
    cells = reviewer.cells_of(notebook(tmp_path))
    assert reviewer.locate("The agent decides which tool to call by reading its own text", cells) == 4
    assert reviewer.locate("the agent decides which tool to call", cells) == 4
    assert reviewer.locate("a totally different sentence about memory stores", cells) is None
    assert reviewer.locate("short", cells) is None


def test_it_is_told_what_it_has_not_read_yet(tmp_path):
    cells = reviewer.cells_of(notebook(tmp_path)) * 6  # 30 cells, more than one window
    seen = [{"tool": "read_cells", "args": {"start": 1}, "text": "cells 1 to 12"}]

    assert "not read past cell 12 of 30" in reviewer.turn("n.ipynb", cells, seen)
    seen.append({"tool": "read_cells", "args": {"start": 19}, "text": "cells 19 to 30"})
    assert "not read past" not in reviewer.turn("n.ipynb", cells, seen)
    # a start the model wrote as words reads as the first window, and does not end the review
    assert "not read past cell 12 of 30" in reviewer.turn("n.ipynb", cells, [
        {"tool": "read_cells", "args": {"start": "the next ones"}, "text": "cells 1 to 12"}])
    assert reviewer.whole("7") == 7 and reviewer.whole(None) == 1 and reviewer.whole(-4) == 1


def test_a_source_it_remembered_keeps_its_link_and_loses_its_date(tmp_path):
    path = notebook(tmp_path)
    proposal = answer("from langchain.agents import create_react_agent",
                      sources=[{"url": "https://arxiv.org/abs/1906.04115", "date": "2023-10-01"}])
    ask = scripted({"tool": "release_notes", "args": {"package": "langchain"}}, proposal)

    source = reviewer.review(path, tools(reviewer.cells_of(path)), ask=ask)["findings"][0]["evidence"][0]
    # nothing it read this run mentions that paper, so the date it gave is nobody's fact
    assert source == {"url": "https://arxiv.org/abs/1906.04115", "date": "unknown", "seen": False}


def test_a_source_it_actually_read_keeps_its_date(tmp_path):
    path = notebook(tmp_path)
    kit = tools(reviewer.cells_of(path))
    kit["release_notes"] = lambda package="": "see https://python.langchain.com/docs/versions/v1_0 for the move"
    proposal = answer("from langchain.agents import create_react_agent",
                      sources=[{"url": "https://python.langchain.com/docs/versions/v1_0", "date": "2026-09-01"}])
    ask = scripted({"tool": "release_notes", "args": {"package": "langchain"}}, proposal)

    entry = reviewer.review(path, kit, ask=ask)
    assert entry["findings"][0]["evidence"][0]["date"] == "2026-09-01"
    assert entry["findings"][0]["evidence"][0]["seen"] is True
    assert entry["recalled"] == 0


def test_research_that_cannot_be_asked_says_so():
    assert "not checked" in reviewer.papers_tool(None)(term="MCP")

    def angry(term):
        raise RuntimeError("arXiv is down")

    assert "could not be checked" in reviewer.papers_tool(angry)(term="MCP")


@pytest.mark.parametrize("bad", [{"answer": {"teaches": "not a list"}}, {"answer": {}}, {}])
def test_nonsense_answers_produce_nothing(tmp_path, bad):
    path = notebook(tmp_path)
    assert reviewer.review(path, tools(reviewer.cells_of(path)), ask=scripted(bad)) is None


@pytest.mark.parametrize("reply", [["x"], "x", 7])
def test_a_reply_that_is_not_an_object_ends_it_without_a_crash(tmp_path, reply):
    path = notebook(tmp_path)
    assert reviewer.review(path, tools(reviewer.cells_of(path)), ask=scripted(reply)) is None


def test_lists_that_are_not_lists_are_refused_not_crashed_on(tmp_path):
    path = notebook(tmp_path)
    cells = reviewer.cells_of(path)
    quote = "from langchain.agents import create_react_agent"

    for reply in ({"answer": {"teaches": 3, "findings": []}},
                  {"answer": {"teaches": [], "findings": 3}},
                  answer(quote, sources=3)):
        entry = reviewer.review(path, tools(cells), ask=scripted(reply))
        assert entry is None or entry["findings"] == []


def test_five_real_words_do_not_make_an_invented_quote_the_notebook_s(tmp_path):
    cells = reviewer.cells_of(notebook(tmp_path))
    invented = "The agent decides which tool to call via OpenAI function calling and stores API keys in plain text"
    assert reviewer.locate(invented, cells) is None


def test_a_source_counts_as_read_only_if_a_tool_other_than_the_notebook_returned_it():
    steps = [{"tool": "read_cells", "args": {"start": 1}, "text": "cell 1: see https://docs.example/agents"},
             {"tool": "release_notes", "args": {"package": "langchain"}, "text": "langchain 1.4.2: agents moved"}]
    assert not reviewer.grounded("https://docs.example/agents", steps)
    assert not reviewer.grounded("https://made.up/docs/agents", steps)

    papers = [{"tool": "papers", "args": {"term": "MCP"},
               "text": "12 papers named mcp in 30 days: on agents 2026-09-01 http://arxiv.org/abs/2609.01234v1"}]
    assert reviewer.grounded("http://arxiv.org/abs/2609.01234v1", papers)
    assert reviewer.grounded("https://arxiv.org/pdf/2609.01234", papers)


def test_the_papers_tool_gives_the_links_it_found():
    tool = reviewer.papers_tool(lambda term: {"papers": 2, "days": 30, "recent": [
        {"title": "On agents", "published": "2026-09-01", "url": "http://arxiv.org/abs/2609.01234v1"}]})
    assert "http://arxiv.org/abs/2609.01234v1" in tool(term="MCP")


def long_notebook(tmp_path, cells=12, lines=150):
    week = tmp_path / "week 3"
    week.mkdir(parents=True, exist_ok=True)
    path = week / "Long.ipynb"
    path.write_text(json.dumps({"cells": [{"cell_type": "code", "source": f"# cell {n}\n" + "x = 1\n" * lines}
                                          for n in range(1, cells + 1)]}), encoding="utf-8")
    return path


def test_no_cell_is_counted_as_read_that_was_never_handed_over(tmp_path):
    # Twelve cells of up to 700 characters do not fit in a 3000-character reply. The
    # reply was cut after it was built, so most cells never reached the model, and it
    # was told it had read them all: 271 of the course's 2000 cells went that way.
    import re

    from src.agents import citations

    cells = reviewer.cells_of(long_notebook(tmp_path))
    said = reviewer.read_cells_tool(cells)(start=1)
    first, last = map(int, re.search(r"cells (\d+) to (\d+) of 12", said).groups())

    assert len(said) <= reviewer.MAX_TOOL_CHARS
    assert first == 1 and last < 12
    assert f"cell {last} (code)" in said and f"cell {last + 1} (code)" not in said
    steps = [citations.step("read_cells", {"start": 1}, said, reviewer.MAX_TOOL_CHARS)]
    assert f"not read past cell {last} of 12" in reviewer.turn("Long.ipynb", cells, steps)


def test_a_cell_too_long_for_one_reply_says_how_much_is_missing(tmp_path):
    cells = reviewer.cells_of(long_notebook(tmp_path, cells=1, lines=900))
    said = reviewer.read_cells_tool(cells)(start=1)

    assert len(said) <= reviewer.MAX_TOOL_CHARS
    assert "more characters" in said and "cells 1 to 1 of 1" in said
