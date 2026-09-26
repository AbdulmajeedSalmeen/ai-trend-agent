import json

from src.notebooks import copies, fingerprint, read_installs, read_patterns, requirements, scan


def notebook(*code, markdown=""):
    cells = [{"cell_type": "code", "source": [line]} for line in code]

    if markdown:
        cells.append({"cell_type": "markdown", "source": [markdown]})

    return {"cells": cells}


def test_an_exact_pin_is_read():
    assert requirements("!pip install langchain==0.0.352") == [("langchain", "==0.0.352")]


def test_a_quoted_wildcard_pin_is_read():
    line = '!pip install -q "langchain==0.3.*" "langchain-openai==0.2.*"'

    assert requirements(line) == [("langchain", "==0.3.*"), ("langchain-openai", "==0.2.*")]


def test_flags_are_not_mistaken_for_packages():
    found = requirements("!pip install -q langchain faiss-cpu --force-reinstall")

    assert [name for name, _ in found] == ["langchain", "faiss-cpu"]


def test_an_underscore_name_becomes_its_pypi_spelling():
    assert requirements("!pip install langchain_community")[0][0] == "langchain-community"


def test_an_extras_bracket_is_stripped():
    assert requirements('!pip install -qU "langchain[openai]"')[0][0] == "langchain"


def test_a_trailing_comment_is_not_parsed_as_packages():
    found = requirements("!pip install mypy_extensions ### Install the missing package")

    assert [name for name, _ in found] == ["mypy-extensions"]


def test_an_install_through_sys_executable_is_read():
    found = requirements('!{sys.executable} -m pip install -q "torchao>=0.16.0"')

    assert found[0][0] == "torchao"


def test_a_line_that_is_not_an_install_yields_nothing():
    assert requirements("print('pip install langchain')") == []


def test_a_package_without_a_bound_is_recorded_as_unpinned():
    installs = read_installs(["!pip install -U langchain langchain-openai"])

    assert installs["pinned"] == {}
    assert installs["unpinned"] == ["langchain", "langchain-openai"]


def test_a_bound_wins_over_an_earlier_unpinned_install():
    installs = read_installs(["!pip install langchain", '!pip install "langchain==0.3.*"'])

    assert installs["pinned"] == {"langchain": "0.3.*"}
    assert installs["unpinned"] == []


def test_a_range_is_kept_as_the_notebook_writes_it():
    installs = read_installs(['!pip install -q "langchain>=0.1.0,<1.0"'])

    assert installs["pinned"] == {"langchain": ">=0.1.0,<1.0"}


def test_a_commented_out_install_is_ignored():
    assert read_installs(["# !pip install transformers"])["unpinned"] == []


def test_a_removed_api_is_flagged_with_its_package():
    found = read_patterns(["reply = openai.ChatCompletion.create(model=m)"])

    assert found[0]["package"] == "openai"
    assert found[0]["legacy"] is True


def test_a_comment_that_names_an_old_api_is_not_a_call():
    assert read_patterns(["# Note the change from `openai.ChatCompletion.create` to the client"]) == []


def test_a_longer_name_is_not_the_removed_one():
    assert read_patterns(["graph = MessageGraphBuilder()"]) == []


def test_langchain_imports_are_left_to_the_release_check():
    """Matched by name, RetrievalQA read as removed even when the notebook
    imported it from langchain_classic, where it still works."""
    found = read_patterns(["from langchain_classic.chains import RetrievalQA\nqa = RetrievalQA.from_chain_type(llm)"])

    assert [pattern for pattern in found if pattern["legacy"]] == []


def test_a_current_api_is_not_flagged():
    found = read_patterns(["graph = StateGraph(State)"])

    assert found[0]["legacy"] is False


def test_prose_about_an_old_api_is_not_code():
    report = scan(notebook("client.chat.completions.create()", markdown="We used to call openai.ChatCompletion"))

    assert [p["uses"] for p in report["patterns"]] == ["client.chat.completions"]


def test_scanning_reports_installs_and_patterns_together():
    report = scan(notebook("!pip install openai==0.28\n", "reply = openai.ChatCompletion.create()\n"))

    assert report["pinned"] == {"openai": "0.28"}
    assert report["patterns"][0]["uses"] == "openai.ChatCompletion"


def write_notebook(path, *sources):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cells": [{"cell_type": "code", "source": source} for source in sources]}),
                    encoding="utf-8")
    return path


def test_two_notebooks_with_the_same_cells_share_a_fingerprint_whatever_their_names():
    a = {"cells": [{"cell_type": "code", "source": ["x = 1\n", "y = 2"]}]}
    b = {"cells": [{"cell_type": "code", "source": "x = 1\ny = 2"}]}
    c = {"cells": [{"cell_type": "markdown", "source": "x = 1\ny = 2"}]}

    assert fingerprint(a) == fingerprint(b) != fingerprint(c)


def test_a_copy_names_the_notebook_a_download_did_not_number(tmp_path):
    week = tmp_path / "week 5"
    files = [write_notebook(week / "Demo (1).ipynb", "print(1)"), write_notebook(week / "Demo.ipynb", "print(1)"),
             write_notebook(week / "Other.ipynb", "print(2)")]

    found = copies(files)

    assert found == [{"notebook": (week / "Demo (1).ipynb").as_posix(),
                      "same_as": (week / "Demo.ipynb").as_posix(), "cells": 1}]
