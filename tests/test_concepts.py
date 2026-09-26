import json
import re
from collections import Counter

from src import concepts
from tests.test_arabic import same_numbers

DASH = re.compile("[–—]")


def installs(*pins):
    return [{"pinned": dict(pin), "unpinned": []} if pin else {"pinned": {}, "unpinned": ["langchain"]}
            for pin in pins]


def test_the_course_version_is_the_newest_release_its_most_common_pin_allows():
    releases = ["0.2.5", "0.3.1", "0.3.30", "0.3.31rc1", "1.4.2"]
    notebooks = installs([("langchain", "0.3.*")], [("langchain", "0.3.*")], [("langchain", ">=0.1.0,<1.0")], None)

    assert concepts.course_version("langchain", notebooks, releases) == "0.3.30"


def test_notebooks_that_never_pin_a_tool_say_nothing_about_its_version():
    assert concepts.course_version("langchain", installs(None, None), ["0.3.30", "1.4.2"]) is None


def test_a_concept_is_searched_by_the_acronym_its_own_docstring_uses():
    summary = "LangChain MCP adapters for connecting MCP servers with LangChain applications."

    assert concepts.search_term("mcp", summary) == "MCP"
    assert concepts.search_term("messages", "Message and message content types.") is None


def test_the_description_is_the_first_paragraph_of_the_module_docstring():
    source = '"""Streaming infrastructure for LangGraph.\n\nMore detail."""\nimport x\n'

    assert concepts.first_sentence(source) == "Streaming infrastructure for LangGraph."
    assert concepts.first_sentence("import x\n") is None


def test_a_notebook_that_explains_a_concept_in_prose_counts_as_covering_it():
    texts = ["We connect an MCP server here.", "from langchain.mcp import x", "compare MCPX and SMCP", "nothing"]

    assert concepts.mentions(texts, "langchain.mcp", "MCP") == 2


def test_demand_decides_between_a_lesson_optional_content_and_watching():
    base = {"notebooks": 0}

    assert concepts.decide({**base, "jobs": 20}) == "add_new_lesson"
    assert concepts.decide({**base, "jobs": 3}) == "add_optional_content"
    assert concepts.decide({**base, "jobs": 0}) == "watch"
    assert concepts.decide({**base, "jobs": None}) == "watch"
    assert concepts.decide({"notebooks": 4, "jobs": 20}) == "watch"


def fake_listing(url, ref):
    listings = {
        ("libs/langchain/langchain", "langchain==0.3.30"): ["agents", "chains", "memory.py"],
        ("libs/langchain_v1/langchain", "langchain==1.4.2"): ["agents", "mcp", "rate_limiters", "_internal", "undocumented"],
        ("libs/langgraph/langgraph", "0.2.76"): ["graph"],
        ("libs/langgraph/langgraph", "1.2.12"): ["graph"],
    }
    for (root, tag), names in listings.items():
        if url.endswith(f"/contents/{root}") and ref == tag:
            return [{"name": name, "type": "file" if name.endswith(".py") else "dir"} for name in names]
    raise AssertionError(f"unexpected listing {url} {ref}")


def fake_file(url):
    if url.endswith("/mcp/__init__.py"):
        return '"""LangChain MCP adapters for connecting MCP servers with LangChain applications."""\n'
    if url.endswith("/rate_limiters/__init__.py"):
        return '"""Base abstraction and in-memory implementation of rate limiters."""\n'
    if url.endswith("/undocumented/__init__.py"):
        return "import os\n"
    return None


def notebook_files(tmp_path):
    files = []
    for index, (install, text) in enumerate([
        ("!pip install langchain==0.3.*", "from langchain.agents import AgentExecutor"),
        ("!pip install langchain==0.3.* langgraph==0.2.*", "graph = StateGraph(State)"),
    ]):
        path = tmp_path / f"n{index}.ipynb"
        path.write_text(json.dumps({"cells": [{"cell_type": "code", "source": [install]},
                                              {"cell_type": "code", "source": [text]}]}), encoding="utf-8")
        files.append(path)
    return files


def find(tmp_path, jobs=20):
    counted = Counter()

    def count_jobs(term):
        counted[term] += 1
        return jobs

    releases = {"langchain": ["0.3.30", "1.4.2"], "langgraph": ["0.2.76", "1.2.12"]}
    result = concepts.find(notebook_files(tmp_path), fetch_json=fake_listing, fetch_text=fake_file,
                           count_jobs=count_jobs, releases_of=releases.get)
    return result, counted


def test_a_module_the_newest_release_added_becomes_a_concept_with_its_evidence(tmp_path):
    result, counted = find(tmp_path)
    mcp = result["concepts"][0]

    assert mcp["concept"] == "MCP" and mcp["action"] == "add_new_lesson"
    assert (mcp["course_version"], mcp["latest"], mcp["jobs"], mcp["notebooks"]) == ("0.3.30", "1.4.2", 20, 0)
    assert mcp["evidence"][0]["url"].endswith("/tree/langchain%3D%3D1.4.2/libs/langchain_v1/langchain/mcp")
    assert mcp["evidence"][1]["url"].endswith("/tree/langchain%3D%3D0.3.30/libs/langchain/langchain")
    assert result["checked"]["langchain"] == {"course": "0.3.30", "latest": "1.4.2"}
    assert counted == {"MCP": 1}


def test_a_common_word_is_never_counted_and_an_undocumented_module_is_left_out(tmp_path):
    result, _ = find(tmp_path)
    modules = {concept["module"]: concept for concept in result["concepts"]}

    assert set(modules) == {"langchain.mcp", "langchain.rate_limiters"}
    assert modules["langchain.rate_limiters"]["jobs"] is None
    assert modules["langchain.rate_limiters"]["action"] == "watch"


def test_the_reason_carries_the_same_figures_in_both_languages(tmp_path):
    for jobs in (0, 1, 2, 20):
        result, _ = find(tmp_path, jobs=jobs)

        for concept in result["concepts"]:
            english, arabic_reason = concepts.why(concept)

            assert same_numbers(english, arabic_reason), (english, arabic_reason)
            assert re.search("[؀-ۿ]", arabic_reason)
            assert not DASH.search(english + arabic_reason)


def test_two_job_posts_take_the_dual_verb(tmp_path):
    result, _ = find(tmp_path, jobs=2)

    assert "وظيفتان ذكرتا MCP في آخر 3 أشهر." in concepts.why(result["concepts"][0])[1]
