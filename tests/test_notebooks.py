from src.notebooks import find_patterns, find_pins, scan


def notebook(*sources):
    return {"cells": [{"cell_type": "code", "source": list(s)} for s in sources]}


def test_a_pinned_install_is_read():
    assert find_pins("!pip install langchain==0.1.16") == {"langchain": "0.1.16"}


def test_several_packages_on_one_line_are_all_read():
    code = "!pip install -q langchain==0.1.16 langchain-community==0.0.38 faiss-cpu"

    assert find_pins(code) == {"langchain": "0.1.16", "langchain-community": "0.0.38"}


def test_an_extras_bracket_is_stripped():
    assert find_pins("%pip install uvicorn[standard]==0.30.1") == {"uvicorn": "0.30.1"}


def test_an_unpinned_install_records_nothing():
    assert find_pins("!pip install langchain faiss-cpu") == {}


def test_a_version_outside_an_install_line_is_ignored():
    assert find_pins("print('langchain==0.1.16 is what we used last year')") == {}


def test_a_legacy_pattern_is_named_with_its_replacement():
    found = find_patterns("chain = RetrievalQA.from_chain_type(llm=llm)")

    assert found[0]["package"] == "langchain"
    assert "LCEL" in found[0]["note"]


def test_a_current_pattern_is_marked_current():
    found = find_patterns("graph = StateGraph(State)")

    assert found[0]["uses"] == "StateGraph"
    assert found[0]["note"] == "current"


def test_scanning_reads_every_cell():
    report = scan(notebook("!pip install langchain==0.1.16\n", "qa = RetrievalQA.from_chain_type(llm)\n"))

    assert report["pins"] == {"langchain": "0.1.16"}
    assert report["patterns"][0]["uses"] == "RetrievalQA chain"
