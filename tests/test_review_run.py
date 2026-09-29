"""The driver: it must hand the rules the shape they already read.

The reviewer agent answers in its own words, in pairs. The rules in src/review.py were
written for a reviewer's prose and read different names. These tests hold the two
together, by running the real rules over what the driver writes, so a rename on either
side fails here and not in a page that quietly loses half its findings.

Nothing here calls a model: the agent is replaced by a function that returns a fixed
entry, the way the model is scripted in the agent's own tests.
"""

import json

import pytest

from src import arabic, lessons
from src import review as rules
from src.agents import review_run


def entry(technique="ReAct agent", status="superseded", cell=3, name="Demo_LangChain_Intro.ipynb"):
    return {
        "id": f"week3/{name[:-6]}",
        "title": name[:-6],
        "week": "week 3",
        "notebook": f"notebooks/week 3/{name}",
        "teaches": [{"technique": technique, "as_taught": "builds a ReAct agent with AgentExecutor",
                     "quote": "from langchain.agents import create_react_agent", "cell": cell, "located": True}],
        "findings": [{"technique": technique, "status": status,
                      "now": "create_react_agent with AgentExecutor",
                      "instead": "create_agent, which carries the same loop with a checkpointer",
                      "why1": "The constructor moved to langchain-classic in 1.0.",
                      "confidence": "high", "basis": "read_and_judged",
                      "evidence": [{"url": "https://docs.example/migrate", "date": "2026-09-01"}]}],
        "dropped": 2,
        "recalled": 1,
        "looked": [{"tool": "read_cells", "args": {"start": 1}}],
        "basis": "read_and_judged",
    }


def names(row):
    return row["notebook"].rsplit("/", 1)[-1]


def notebooks(tmp_path, files=("Demo_LangChain_Intro.ipynb", "Demo_RAG.ipynb")):
    week = tmp_path / "week 3"
    week.mkdir(parents=True)
    for name in files:
        (week / name).write_text(json.dumps({"cells": [{"cell_type": "code", "source": "x"}]}), encoding="utf-8")
    return tmp_path


def test_the_rules_can_read_every_field_the_driver_writes():
    page = review_run.entry_for_page(entry())
    finding = page["findings"][0]

    assert rules.week_of(page) == 3
    assert rules.proposed_verdict(page) == "replace"
    taught = {item["technique_id"]: item for item in page["teaches"]}
    assert taught.keys() == {"react-agent"}

    compact = rules.compact(finding, page["notebook"], owned=set(), taught=taught)
    # what the notebook does now, what to teach instead, and one line of why: all present
    assert compact["now"].startswith("builds a ReAct agent")
    assert compact["instead"].startswith("create_agent")
    assert compact["why1"].startswith("The constructor moved")
    assert compact["s"] == "superseded" and compact["cell"] == 3
    assert compact["u"] == "https://docs.example/migrate" and compact["d"] == "2026-09-01"


def test_a_written_lesson_travels_in_the_shape_the_demand_rules_read():
    written = {"title": "Building an agent loop with checkpointers", "term": "checkpointers",
               "why": "The course teaches a constructor that no longer exists.",
               "covers": ["Rebuild the week 3 agent", "Resume a run from its last state"],
               "answers": ["ReAct agent"], "already_in": 0, "looked": []}
    page = review_run.entry_for_page(entry(), written)

    assert sorted(page["new_lesson"]) == ["covers", "title", "why"]
    assert page["lesson_term"] == "checkpointers" and page["lesson_answers"] == ["ReAct agent"]
    # src/lessons.py reads a proposal by title and covers, and nothing else
    assert lessons.proposals({"notebooks": [page]}, copies=set())[0]["title"] == written["title"]

    none = review_run.entry_for_page(entry())
    assert none["new_lesson"] is None and none["lesson_answers"] == []


def test_effort_is_what_the_judge_said_or_says_it_was_assumed():
    weighed = {"worth": 4, "effort": "large", "reason": "six notebooks teach it",
               "cites": [{"factor": "reach", "tool": "course_uses", "quote": "6 notebooks"}],
               "dropped": 0, "looked": []}
    judged = review_run.entry_for_page(entry(), weighed=weighed)

    assert judged["effort"] == "large" and judged["effort_source"] == "judged"
    assert judged["worth"] == 4 and judged["worth_why"] == "six notebooks teach it"
    assert judged["worth_cites"][0]["tool"] == "course_uses"
    # and the page reads effort from the same place it always did
    assert judged["effort"] in arabic.REVIEW_EFFORT

    assumed = review_run.entry_for_page(entry())
    assert assumed["effort"] == "medium" and assumed["effort_source"] == "default"
    assert assumed["worth"] is None and assumed["worth_cites"] == []


def test_a_finding_carries_the_cell_its_technique_was_located_in():
    page = review_run.entry_for_page(entry(cell=11))
    assert page["findings"][0]["cell"] == 11
    assert page["located_claims"] == 1 and page["unlocated_claims"] == 2


@pytest.mark.parametrize("status, verdict", [
    ("superseded", "replace"), ("unsafe", "replace"), ("removed", "replace"),
    ("missing_context", "revise"), ("current", "keep"),
])
def test_it_proposes_from_the_findings_and_never_on_a_lesson_still_current(status, verdict):
    page = review_run.entry_for_page(entry(status=status))
    assert page["verdict"] == verdict
    # and the rules agree, given the same findings
    statuses = {f["status"] for f in page["findings"] if f["status"] in rules.SEVERITY}
    assert rules.decide(page["verdict"], statuses) == verdict


def test_a_lesson_still_current_asks_for_no_edit():
    page = review_run.entry_for_page(entry(status="current"))
    assert page["action"].startswith("Nothing to change")
    assert "Cell" in review_run.entry_for_page(entry())["action"]


def test_two_spellings_of_one_technique_share_an_id():
    assert review_run.slug("ReAct agent") == review_run.slug("ReAct  Agent!")
    assert review_run.slug("") == "" and len(review_run.slug("x" * 200)) == 48


def test_what_it_writes_loads_as_the_file_the_rules_expect(tmp_path):
    out = tmp_path / "material_review.json"
    review_run.write(out, {"a": review_run.entry_for_page(entry()),
                           "b": review_run.entry_for_page(entry(name="Demo_RAG.ipynb"))})

    loaded = rules.load(out)
    assert loaded["schema"] == "material_review/1"
    assert loaded["counts"] == {"notebooks_reviewed": 2, "claims_located_in_a_cell": 2,
                                "claims_dropped_as_unfound": 4, "sources_recalled_not_read": 2,
                                "lessons_written": 0, "effort_judged_not_assumed": 0}


def test_it_resumes_and_does_not_read_a_notebook_twice(tmp_path, monkeypatch):
    root = notebooks(tmp_path)
    out = tmp_path / "out.json"
    read = []

    def fake(path, tools, **kw):
        read.append(path.name)
        return entry(name=path.name)

    monkeypatch.setattr(review_run.reviewer, "review", fake)
    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--no-research"])
    review_run.main()
    assert len(read) == 2

    review_run.main()  # the file is already there
    assert len(read) == 2
    assert len(rules.load(out)["notebooks"]) == 2

    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--no-research", "--again"])
    review_run.main()
    assert len(read) == 4


def test_it_can_be_run_in_batches_and_over_one_notebook(tmp_path, monkeypatch):
    root = notebooks(tmp_path)
    out = tmp_path / "out.json"
    monkeypatch.setattr(review_run.reviewer, "review", lambda path, tools, **kw: entry(name=path.name))

    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--limit", "1"])
    review_run.main()
    assert len(rules.load(out)["notebooks"]) == 1

    one = tmp_path / "one.json"
    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(one), "--only", "rag"])
    review_run.main()
    assert [names(row) for row in rules.load(one)["notebooks"]] == ["Demo_RAG.ipynb"]


def test_a_notebook_it_could_not_locate_anything_in_is_left_out(tmp_path, monkeypatch):
    root = notebooks(tmp_path)
    out = tmp_path / "out.json"
    monkeypatch.setattr(review_run.reviewer, "review", lambda path, tools, **kw: None)
    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out)])
    review_run.main()
    # nothing was read, so nothing is written: no file claims a review that did not happen
    assert not out.exists()


def test_the_default_output_is_not_the_review_the_page_reads():
    # fixtures/material_review.json came from another process, is richer, and is what the
    # page serves. Writing over it is a decision, never a default.
    assert review_run.OUT_PATH != review_run.SERVED_PATH
    with open(".gitignore", encoding="utf-8") as ignored:
        assert str(review_run.OUT_PATH).replace("\\", "/") in ignored.read()


def served(tmp_path):
    """A review this driver did not write, like the one the page serves."""
    out = tmp_path / "material_review.json"
    out.write_text(json.dumps({"schema": "material_review/1", "read_on": "2026-09-26",
                               "source": "the 89 notebooks under notebooks/, read as teaching material",
                               "counts": {"verdicts": {"revise": 1}},
                               "notebooks": [review_run.entry_for_page(entry())]}), encoding="utf-8")
    return out


def test_a_review_something_else_wrote_is_left_alone(tmp_path, monkeypatch):
    root = notebooks(tmp_path)
    out = served(tmp_path)
    before = out.read_bytes()
    monkeypatch.setattr(review_run.reviewer, "review", lambda path, tools, **kw: entry(name=path.name))

    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out)])
    with pytest.raises(SystemExit):
        review_run.main()
    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--again"])
    with pytest.raises(SystemExit):
        review_run.main()
    assert out.read_bytes() == before

    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--replace"])
    review_run.main()
    assert rules.load(out)["source"] == review_run.SOURCE


def test_a_file_it_cannot_read_is_never_written_over(tmp_path):
    out = tmp_path / "out.json"
    out.write_text('{"schema": "material_review/1", "notebo', encoding="utf-8")
    with pytest.raises(SystemExit):
        review_run.load_existing(out)
    assert out.read_text(encoding="utf-8") == '{"schema": "material_review/1", "notebo'
    assert review_run.load_existing(tmp_path / "nothing.json") == {}


def test_a_run_that_reads_nothing_new_leaves_the_file_as_it_was(tmp_path, monkeypatch):
    root = notebooks(tmp_path)
    out = tmp_path / "out.json"
    monkeypatch.setattr(review_run.reviewer, "review", lambda path, tools, **kw: entry(name=path.name))
    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--no-research"])
    review_run.main()
    before = out.read_bytes()

    review_run.main()  # every notebook is already there
    assert out.read_bytes() == before


def test_reading_one_notebook_again_keeps_the_others(tmp_path, monkeypatch):
    root = notebooks(tmp_path)
    out = tmp_path / "out.json"
    monkeypatch.setattr(review_run.reviewer, "review", lambda path, tools, **kw: entry(name=path.name))
    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--no-research"])
    review_run.main()

    monkeypatch.setattr(review_run.reviewer, "review",
                        lambda path, tools, **kw: entry(name=path.name, status="deprecated"))
    monkeypatch.setattr("sys.argv", ["x", "--notebooks", str(root), "--out", str(out), "--no-research",
                                     "--again", "--only", "rag"])
    review_run.main()

    rows = {names(row): row for row in rules.load(out)["notebooks"]}
    assert sorted(rows) == ["Demo_LangChain_Intro.ipynb", "Demo_RAG.ipynb"]
    assert rows["Demo_RAG.ipynb"]["findings"][0]["status"] == "deprecated"
    assert rows["Demo_LangChain_Intro.ipynb"]["findings"][0]["status"] == "superseded"
    assert not list(tmp_path.glob("*.tmp"))


def test_research_is_only_wired_up_when_asked(tmp_path):
    path = notebooks(tmp_path) / "week 3" / "Demo_RAG.ipynb"
    assert "not checked" in review_run.tools_for(path, None, research=False)["papers"](term="MCP")
    assert "no releases" in review_run.tools_for(path, None, research=True)["release_notes"](package="langchain")
    assert set(review_run.tools_for(path, None, research=True)) == {"read_cells", "release_notes", "papers"}
