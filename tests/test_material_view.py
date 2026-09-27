import re

from src import material_view, review

DASH = re.compile("[–—]")

TABLE = {"source": "https://example.com/deprecations", "read_on": "2026-09-26", "retirements": [
    {"shutdown": "2026-10-23", "announced": "2026-04-22", "ids": ["gpt-3.5-turbo"], "replacement": "gpt-5.6-terra"},
    {"shutdown": "2026-09-28", "announced": "2025-09-26", "ids": ["gpt-3.5-turbo-instruct"],
     "replacement": "gpt-5.6-terra"},
]}


def curriculum():
    return {
        "chapters": [
            {"chapter_id": "C8", "week": 3, "title": "Week 3 - LangChain", "notebooks": ["chat.ipynb", "intro.ipynb"],
             "material_edits": [{"notebook": "notebooks/week 3/chat.ipynb", "cell": 93, "kind": "replace",
                                 "current": "from langchain.chains import RetrievalQA",
                                 "proposed": "from langchain_classic.chains import RetrievalQA",
                                 "reason": "moved", "reason_ar": "انتقلت", "evidence_url": "https://example.com/tag",
                                 "checked": "langchain 1.4.2", "runs_as_pinned": False}]},
            {"chapter_id": "C12", "week": 4, "title": "Week 4 - Agents", "notebooks": ["agent.ipynb", "agent (1).ipynb"],
             "material_edits": []},
            {"chapter_id": "C1", "week": 1, "title": "Week 1 - Setup", "notebooks": [], "material_edits": []},
        ],
        "model_calls": [
            {"notebook": "notebooks/week 3/chat.ipynb", "calls": [
                {"model": "gpt-3.5-turbo", "cell": 57, "how": "default", "constructor": "ChatOpenAI"},
                {"model": "gpt-4o-mini", "cell": 60, "how": "named"}]},
            {"notebook": "notebooks/week 3/intro.ipynb", "calls": [
                {"model": "gpt-3.5-turbo-instruct", "cell": 9, "how": "default", "constructor": "OpenAI"},
                {"model": "gpt-3.5-turbo-instruct", "cell": 9, "how": "default", "constructor": "OpenAI"}]},
            {"notebook": "notebooks/week 4/agent (1).ipynb", "calls": [{"model": "gpt-3.5-turbo", "cell": 8, "how": "named"}]},
        ],
        "copies": [{"notebook": "notebooks/week 4/agent (1).ipynb", "same_as": "notebooks/week 4/agent.ipynb", "cells": 3}],
    }


def reviewed():
    material = {"schema": review.SCHEMA, "read_on": "2026-09-26", "notebooks": [
        {"id": "week3/chat", "notebook": "notebooks/week 3/chat.ipynb", "week_number": 3, "verdict": "replace",
         "findings": [
             {"technique": "RetrievalQA over FAISS", "status": "superseded", "cell": 93, "confidence": "high"},
             {"technique": "Whole-notebook framing", "status": "missing_context", "cell": None},
             {"technique": "Chat model default", "status": "deprecated", "cell": 70}]},
    ]}
    return review.build(material, curriculum(), [], TABLE)


def book(view, name):
    return next(b for chapter in view["chapters"] for b in chapter["books"] if b["file"] == name)


def test_without_the_review_every_notebook_is_listed_with_its_verified_cells():
    view = material_view.view(curriculum(), TABLE, [], None)
    chat = book(view, "chat.ipynb")

    assert view["reviewed"] is False
    assert [chapter["id"] for chapter in view["chapters"]] == ["C8", "C12"]
    assert [cell["cell"] for cell in chat["cells"]] == [57, 93]
    assert all(item["basis"] == "verified" for cell in chat["cells"] for item in cell["items"])


def test_an_import_change_carries_its_lines_its_source_and_whether_it_breaks_today():
    chat = book(material_view.view(curriculum(), TABLE, [], None), "chat.ipynb")
    item = next(cell for cell in chat["cells"] if cell["cell"] == 93)["items"][0]

    assert item["kind"] == "import" and item["breaks"] is True
    assert item["proposed"] == "from langchain_classic.chains import RetrievalQA"
    assert item["u"] == "https://example.com/tag"


def test_a_model_change_names_the_shutdown_and_the_vendor_replacement_in_both_languages():
    chat = book(material_view.view(curriculum(), TABLE, [], None), "chat.ipynb")
    item = next(cell for cell in chat["cells"] if cell["cell"] == 57)["items"][0]

    assert item["kind"] == "model" and item["shutdown"] == "2026-10-23" and item["replacement"] == "gpt-5.6-terra"
    assert item["why"].startswith("Cell 57 calls LangChain's ChatOpenAI() with no model")
    assert "2026-10-23" in item["why_ar"] and not DASH.search(item["why"] + item["why_ar"])


def test_a_model_on_no_list_is_not_a_change():
    chat = book(material_view.view(curriculum(), TABLE, [], None), "chat.ipynb")

    assert 60 not in [cell["cell"] for cell in chat["cells"]]


def test_the_same_call_twice_in_a_cell_is_one_change():
    intro = book(material_view.view(curriculum(), TABLE, [], None), "intro.ipynb")

    assert len(intro["cells"]) == 1 and len(intro["cells"][0]["items"]) == 1


def test_a_copy_has_no_cells_of_its_own():
    copy = book(material_view.view(curriculum(), TABLE, [], None), "agent (1).ipynb")

    assert copy["copy_of"] == "agent.ipynb" and copy["cells"] == []


def test_with_the_review_judged_findings_join_their_cells_after_the_verified_ones():
    view = material_view.view(curriculum(), TABLE, [], reviewed())
    chat = book(view, "chat.ipynb")
    cell = next(cell for cell in chat["cells"] if cell["cell"] == 93)

    assert view["reviewed"] is True
    assert [item["kind"] for item in cell["items"]] == ["import", "method"]
    assert cell["items"][1]["basis"] == "read_and_judged"
    assert [item["t"] for item in chat["whole"]] == ["Whole-notebook framing"]
    assert chat["v"] == "replace"


def test_the_summary_counts_what_the_view_carries():
    view = material_view.view(curriculum(), TABLE, [{"date": "2026-10-23", "books": 1}], reviewed())
    summary = view["summary"]
    cells = [cell for chapter in view["chapters"] for b in chapter["books"] if not b["copy_of"] for cell in b["cells"]]

    assert summary["cells"] == len(cells) == 4
    assert summary["cells_verified"] == 3 and summary["cells_judged"] == 1
    assert summary["breaks_today"] == 1 and summary["copies"] == 1
    assert summary["stop_running"] == [{"date": "2026-10-23", "notebooks": 1}]
