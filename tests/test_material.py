import re

from src import material

DASH = re.compile("[–—]")


def release(package, version, files):
    """A release whose files are the ones given, keyed by path under the package."""
    root = material.SOURCES[package][1]

    def fetch(url):
        for relative, text in files.items():
            if url.endswith(f"/{root}/{relative}"):
                return text
        return None

    return material.Release(package, version, fetch)


def releases():
    lazy_chains = ("_module_lookup = {'RetrievalQA': 'langchain_classic.chains.retrieval_qa.base'}\n"
                   "def __getattr__(name):\n    return name\n"
                   "__all__ = list(_module_lookup.keys())\n")
    return {
        "langchain": release("langchain", "1.4.2", {
            "__init__.py": '__version__ = "1.4.2"\n',
            "agents/__init__.py": "from langchain.agents.factory import create_agent\n__all__ = ['create_agent']\n",
            "tools/__init__.py": "__all__ = ['tool']\n",
        }),
        "langchain_core": release("langchain_core", "1.6.4", {
            "__init__.py": "",
            "prompts/__init__.py": "__all__ = ['PromptTemplate']\n",
        }),
        "langchain_openai": release("langchain_openai", "1.6.3", {
            "__init__.py": "from langchain_openai.chat_models import ChatOpenAI\n",
        }),
        "langchain_classic": release("langchain_classic", "1.0.8", {
            "__init__.py": "",
            "hub.py": "def pull(name):\n    return name\n",
            "agents/__init__.py": "from langchain_classic.agents.agent import AgentExecutor\n",
            "chains/__init__.py": lazy_chains,
        }),
    }


def check(line):
    return material.check_import(material.import_statements(line)[0], releases())


def test_a_name_the_release_still_exports_needs_no_edit():
    assert check("from langchain.agents import create_agent") is None


def test_a_name_that_moved_is_proposed_from_where_the_release_has_it_now():
    edit = check("from langchain.agents import AgentExecutor")

    assert edit["proposed"] == "from langchain_classic.agents import AgentExecutor"
    assert "langchain 1.4.2" in edit["reason"] and "langchain-classic 1.0.8" in edit["reason"]
    assert "langchain-classic%3D%3D1.0.8" in edit["moved_to"][0]["url"]


def test_a_module_the_release_dropped_is_said_to_be_gone():
    edit = check("from langchain.prompts import PromptTemplate")

    assert edit["proposed"] == "from langchain_core.prompts import PromptTemplate"
    assert "has no langchain.prompts module" in edit["reason"]
    assert edit["evidence_url"].endswith("/tree/langchain%3D%3D1.4.2/libs/langchain_v1/langchain")


def test_names_that_stay_keep_their_own_line():
    edit = check("from langchain.agents import create_agent, AgentExecutor")

    assert edit["proposed"] == ("from langchain.agents import create_agent\n"
                                "from langchain_classic.agents import AgentExecutor")
    assert edit["names"] == ["AgentExecutor"]


def test_a_submodule_imported_by_name_is_found_where_it_moved():
    edit = check("from langchain import hub")

    assert edit["proposed"] == "from langchain_classic import hub"
    assert edit["reason"].startswith("langchain 1.4.2 no longer has hub.")
    assert edit["moved_to"][0]["url"].endswith("/langchain_classic/hub.py")


def test_a_name_a_module_loads_lazily_counts_as_there():
    assert check("from langchain.chains import RetrievalQA")["proposed"] == \
        "from langchain_classic.chains import RetrievalQA"


def test_an_alias_and_a_parenthesised_list_survive_the_edit():
    source = "from langchain.agents import (\n    AgentExecutor as Executor,\n    create_agent,\n)\nx = 1"
    statement = material.import_statements(source)[0]
    edit = material.check_import(statement, releases())

    assert statement["current"] == "from langchain.agents import (\n    AgentExecutor as Executor,\n    create_agent,\n)"
    assert edit["proposed"] == ("from langchain.agents import create_agent\n"
                                "from langchain_classic.agents import AgentExecutor as Executor")


def test_a_name_found_nowhere_is_said_plainly_rather_than_guessed():
    edit = check("from langchain.agents import Vanished")

    assert edit["proposed"] == "# Vanished: not found in any release we read"
    assert "none of the releases we read" in edit["reason"]


def test_every_reason_has_its_arabic_without_a_long_dash():
    for line in ["from langchain.agents import AgentExecutor", "from langchain.prompts import PromptTemplate",
                 "from langchain import hub", "from langchain.agents import Vanished"]:
        edit = check(line)

        assert re.search("[؀-ۿ]", edit["reason_ar"])
        assert not DASH.search(edit["reason"] + edit["reason_ar"])


def test_a_notebook_pinned_below_the_release_runs_as_pinned():
    assert material.keeps_old_line("0.3.*", "1.4.2") is True
    assert material.keeps_old_line(">=0.1.0,<1.0", "1.4.2") is True
    assert material.keeps_old_line(">=0.1", "1.4.2") is False
    assert material.keeps_old_line("unpinned", "1.4.2") is False
    assert material.keeps_old_line(None, "1.4.2") is None


def notebook(install):
    return {"cells": [
        {"cell_type": "markdown", "source": "# Document QA"},
        {"cell_type": "code", "source": [f"!pip install {install} langchain-openai\n"]},
        {"cell_type": "code", "source": ["from langchain.chains import RetrievalQA\n"]},
    ]}


def test_cells_are_counted_from_the_top_the_way_a_teacher_scrolls():
    edits = material.check_notebook(material.Path("notebooks/week 3/qa.ipynb"), notebook("langchain==0.3.*"), releases())

    assert [edit["cell"] for edit in edits] == [3]
    assert edits[0]["runs_as_pinned"] is True
    assert edits[0]["notebook"] == "notebooks/week 3/qa.ipynb"


def test_a_notebook_that_breaks_today_is_also_told_what_to_install():
    edits = material.check_notebook(material.Path("notebooks/week 3/qa.ipynb"), notebook("langchain"), releases())

    assert [edit["cell"] for edit in edits] == [2, 3]
    assert edits[0]["proposed"] == "!pip install langchain langchain-openai langchain-classic"
    assert all(edit["runs_as_pinned"] is False for edit in edits)
