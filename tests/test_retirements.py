import json
import re
from datetime import date

from src import retirements

DASH = re.compile("[–—]")

DEFAULTS = {"OpenAI": {"model": "gpt-3.5-turbo-instruct"}, "ChatOpenAI": {"model": "gpt-3.5-turbo"}}

TABLE = {"source": "https://example.com/deprecations", "read_on": "2026-09-26", "defaults": DEFAULTS,
         "retirements": [
             {"shutdown": "2026-09-28", "announced": "2025-09-26", "ids": ["gpt-3.5-turbo-instruct"],
              "replacement": "gpt-5.6-terra"},
             {"shutdown": "2026-10-23", "announced": "2026-04-22", "ids": ["gpt-3.5-turbo-0125", "gpt-3.5-turbo"],
              "replacement": "gpt-5.6-terra"},
             {"shutdown": "2026-10-23", "announced": "2026-04-22", "ids": ["gpt-4-0613", "gpt-4"],
              "replacement": "gpt-5.6-sol"},
         ]}


def notebook(*cells):
    return {"cells": [{"cell_type": kind, "source": source} for kind, source in cells]}


def test_a_model_named_in_quotes_is_a_call_with_its_cell():
    found = retirements.calls(notebook(("markdown", "intro"), ("code", 'llm = ChatOpenAI(model="gpt-4")')), {})

    assert found == [{"model": "gpt-4", "cell": 2, "how": "named"}]


def test_prose_and_comments_are_not_calls():
    found = retirements.calls(notebook(
        ("markdown", 'We use "gpt-4" here.'),
        ("code", '# model="gpt-4" was the old choice\nprint("GPT-5 by OpenAI")')), {})

    assert found == []


def test_a_langchain_constructor_with_no_model_reaches_its_default():
    found = retirements.calls(notebook(
        ("code", "from langchain_openai import OpenAI"),
        ("code", "llm = OpenAI(temperature=float(0.9))")), DEFAULTS)

    assert found == [{"model": "gpt-3.5-turbo-instruct", "cell": 2, "how": "default", "constructor": "OpenAI"}]


def test_a_constructor_that_names_its_model_does_not_reach_the_default():
    found = retirements.calls(notebook(
        ("code", "from langchain_openai import ChatOpenAI\nllm = ChatOpenAI(model='gpt-4o-mini')")), DEFAULTS)

    assert [call["how"] for call in found] == ["named"]


def test_the_sdk_client_has_no_default_model():
    found = retirements.calls(notebook(("code", "from openai import OpenAI\nclient = OpenAI()")), DEFAULTS)

    assert found == []


def test_a_name_imported_from_both_the_sdk_and_langchain_is_not_guessed_at():
    found = retirements.calls(notebook(
        ("code", "from openai import OpenAI\nfrom langchain_openai import OpenAI\nllm = OpenAI()")), DEFAULTS)

    assert found == []


def model_calls():
    return [
        {"notebook": "notebooks/week 3/a.ipynb", "calls": [{"model": "gpt-3.5-turbo", "cell": 4, "how": "named"},
                                                            {"model": "gpt-4o-mini", "cell": 5, "how": "named"}]},
        {"notebook": "notebooks/week 3/b.ipynb", "calls": [{"model": "gpt-4", "cell": 2, "how": "named"}]},
        {"notebook": "notebooks/week 3/c.ipynb", "calls": [{"model": "gpt-3.5-turbo-instruct", "cell": 9,
                                                            "how": "default", "constructor": "OpenAI"}]},
        {"notebook": "notebooks/week 5/b (1).ipynb", "calls": [{"model": "gpt-4", "cell": 2, "how": "named"}]},
    ]


def test_deadlines_count_each_notebook_once_per_date_soonest_first():
    found = retirements.deadlines(model_calls(), TABLE, {"notebooks/week 5/b (1).ipynb"})

    assert [(d["date"], d["books"], d["named"], d["by_default"]) for d in found] == [
        ("2026-09-28", 1, 0, 1), ("2026-10-23", 2, 2, 0)]
    assert found[1]["what"] == "gpt-3.5-turbo, gpt-4"


def test_a_model_on_no_list_reaches_no_deadline():
    found = retirements.deadlines([{"notebook": "x", "calls": [{"model": "gpt-5-mini", "cell": 1, "how": "named"}]}],
                                  TABLE)

    assert found == []


def test_each_deadline_says_how_it_was_reached_in_both_languages():
    soon, later = retirements.deadlines(model_calls(), TABLE)

    assert soon["why"] == ("1 notebook calls LangChain's OpenAI() with no model, which defaults to "
                           "gpt-3.5-turbo-instruct. OpenAI shuts it down on 2026-09-28.")
    assert later["why"].startswith("3 notebooks name gpt-3.5-turbo or gpt-4 in a code cell")
    assert later["why"].endswith("OpenAI shuts them down on 2026-10-23.")
    assert "2026-09-28" in soon["why_ar"] and "OpenAI()" in soon["why_ar"]
    assert not any(DASH.search(d["why_ar"]) for d in (soon, later))


def test_no_table_means_no_deadlines():
    assert retirements.deadlines(model_calls(), None) == []


def test_the_recorded_table_is_well_formed():
    data = json.loads(retirements.RETIREMENTS_PATH.read_text(encoding="utf-8"))
    ids = [model for row in data["retirements"] for model in row["ids"]]

    assert len(ids) == len(set(ids))
    assert all(date.fromisoformat(row["announced"]) < date.fromisoformat(row["shutdown"])
               for row in data["retirements"])
    assert data["source"].startswith("https://") and date.fromisoformat(data["read_on"])
    assert set(data["defaults"]) == {"OpenAI", "ChatOpenAI"}
