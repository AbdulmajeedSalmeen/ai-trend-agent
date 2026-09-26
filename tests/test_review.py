import json
import re

import pytest

from src import arabic, review

DASH = re.compile("[–—]")
HINDI_DIGIT = re.compile("[٠-٩]")

SHUTDOWNS = {"retirements": [
    {"shutdown": "2026-10-23", "announced": "2026-04-22", "ids": ["gpt-3.5-turbo-0125", "gpt-3.5-turbo"],
     "replacement": "gpt-5.6-terra"},
    {"shutdown": "2026-01-10", "announced": "2025-06-01", "ids": ["gpt-old"], "replacement": "gpt-5.6-terra"},
]}


def curriculum():
    return {"chapters": [
        {"chapter_id": "C4", "week": 2, "title": "Week 2 - BERT", "notebooks": ["bert.ipynb"],
         "material_edits": [{"notebook": "notebooks/week 2/bert.ipynb", "cell": 7}]},
        {"chapter_id": "C12", "week": 4, "title": "Week 4 - Agents",
         "notebooks": ["agent.ipynb", "agent (1).ipynb"], "material_edits": []},
        {"chapter_id": "C10", "week": 4, "title": "Week 4 - Tools", "notebooks": ["tools.ipynb"],
         "material_edits": []},
    ], "copies": [{"notebook": "notebooks/week 4/agent (1).ipynb",
                   "same_as": "notebooks/week 4/agent.ipynb", "cells": 3}]}


def finding(status, technique="Technique", cell=None, technique_id=None, confidence="high",
            what_changed="What changed.", date="2026-09-01"):
    return {"technique": technique, "technique_id": technique_id or technique.lower(), "status": status,
            "what_changed": what_changed, "replacement": "`new_thing` instead", "replacement_name": "new_thing",
            "cell": cell, "confidence": confidence, "basis": "read_and_judged",
            "evidence": [{"url": "https://example.com/source", "date": date, "quote": "short"}]}


def entry(week, name, verdict, findings, chapter_id="C99", **extra):
    return {"id": f"week{week}/{name}", "notebook": f"notebooks/week {week}/{name}.ipynb", "week": f"week {week}",
            "week_number": week, "chapter_id": chapter_id, "verdict": verdict, "action": "Do the thing.",
            "effort": "medium", "new_lesson": None, "findings": findings, "located_claims": 3,
            "unlocated_claims": 1, **extra}


def view(*entries, retirements=None):
    data = {"schema": review.SCHEMA, "read_on": "2026-09-26", "notebooks": list(entries)}
    return review.build(data, curriculum(), [], retirements)


def book(result, name):
    return next(b for chapter in result["chapters"] for b in chapter["books"] if b["file"] == f"{name}.ipynb")


def test_replace_and_retire_need_a_hard_finding():
    assert review.decide("replace", {"missing_context"}) == "revise"
    assert review.decide("retire", {"missing_context"}) == "revise"
    assert review.decide("replace", {"missing_context", "superseded"}) == "replace"
    assert review.decide("retire", {"unsafe"}) == "retire"


def test_a_verdict_with_nothing_behind_it_is_keep():
    assert review.decide("revise", set()) == "keep"
    assert review.decide("keep", set()) == "keep"


def test_an_unknown_verdict_is_read_as_revise():
    assert review.decide("rewrite", {"removed"}) == "revise"


def test_a_lowering_recorded_by_an_earlier_pass_is_still_counted():
    lowered = entry(4, "tools", "revise", [finding("missing_context")],
                    verdict_note="lowered from replace: every finding is an absence")
    result = view(lowered)

    assert result["counts"]["lowered"] == 1
    assert book(result, "tools")["proposed"] == "replace"
    assert "lowered it to revise" in book(result, "tools")["why"]


def test_the_chapter_comes_from_the_curriculum_not_the_reviewer():
    result = view(entry(2, "bert", "revise", [finding("superseded", cell=3)], chapter_id="C25"))

    assert book(result, "bert")["ch"] == "C4"


def test_a_notebook_no_chapter_holds_is_listed_apart_and_still_counted():
    result = view(entry(6, "stray", "revise", [finding("superseded")]))

    assert result["unplaced"][0]["file"] == "stray.ipynb"
    assert result["counts"]["unplaced"] == 1
    assert result["counts"]["notebooks"] == 1


def test_a_copy_is_retired_and_its_findings_are_counted_once():
    original = entry(4, "agent", "revise", [finding("superseded", cell=2)])
    copy = entry(4, "agent (1)", "revise", [finding("superseded", cell=2)])
    result = view(original, copy)
    duplicate = book(result, "agent (1)")

    assert duplicate["v"] == "retire"
    assert duplicate["copy_of"] == "agent.ipynb"
    assert duplicate["f"] == [] and duplicate["found"] == 0
    assert result["counts"]["statuses"] == {"superseded": 1}
    assert result["counts"]["claims"] == 4
    assert result["counts"]["copies"] == 1


def test_a_credential_finding_is_counted_never_located_and_still_hard():
    key = finding("unsafe", technique="Hardcoded API key in a cell", cell=4)
    result = view(entry(4, "tools", "replace", [key, finding("missing_context", cell=5)]))
    tools = book(result, "tools")

    assert result["counts"]["credentials"] == 1
    assert all("API key" not in f["t"] for f in tools["f"])
    assert tools["v"] == "replace"


def test_a_finding_on_a_cell_the_import_check_edits_says_so():
    result = view(entry(2, "bert", "revise", [finding("superseded", cell=7), finding("superseded", "Other", cell=8)]))
    owned = {f["cell"]: f["own"] for f in book(result, "bert")["f"]}

    assert owned == {7: True, 8: False}
    assert result["counts"]["owned_by_import_check"] == 1


def test_current_findings_are_not_shown_and_the_most_serious_come_first():
    findings = [finding("missing_context", "A"), finding("current", "B"), finding("superseded", "C"),
                finding("unsafe", "D"), finding("removed", "E"), finding("deprecated", "F")]
    tools = book(view(entry(4, "tools", "revise", findings)), "tools")

    assert [f["s"] for f in tools["f"]] == ["unsafe", "removed", "deprecated", "superseded"]
    assert tools["found"] == 5 and tools["more"] == 1


def test_the_counts_agree_with_what_travels():
    findings = [finding("superseded", "A", cell=1), finding("unsafe", "B"), finding("deprecated", "C", cell=3),
                finding("missing_context", "D", cell=4), finding("removed", "E", cell=5)]
    result = view(entry(4, "tools", "replace", findings), entry(2, "bert", "revise", [finding("superseded")]))
    counts = result["counts"]

    assert sum(counts["statuses"].values()) == counts["anchored"] + counts["whole_notebook"] == 6
    assert result["shown"] == sum(len(b["f"]) for c in result["chapters"] for b in c["books"]) == 5
    assert counts["claims"] == counts["located"] + counts["dropped"]


def test_an_undated_source_travels_as_none_and_is_counted():
    result = view(entry(4, "tools", "revise", [finding("superseded", date="unknown")]))

    assert book(result, "tools")["f"][0]["d"] is None
    assert result["counts"]["undated_sources"] == 1


def test_removed_is_relabelled_deprecated_while_the_vendor_shutdown_is_ahead():
    named = finding("removed", technique="gpt-3.5-turbo as the agent's model")
    dated = finding("removed", technique="Model choice",
                    what_changed="gpt-3.5-turbo is named, and OpenAI shuts it down on 23 October 2026.")
    past = finding("removed", technique="gpt-old as the model")
    elsewhere = finding("removed", technique="RetrievalQA", what_changed="Moved out of langchain in 1.0.")
    result = view(entry(4, "tools", "revise", [named, dated, past, elsewhere]), retirements=SHUTDOWNS)

    assert result["counts"]["statuses"] == {"deprecated": 2, "removed": 2}
    assert result["counts"]["relabelled"] == 2
    assert sorted(f["was"] or "" for f in book(result, "tools")["f"]) == ["", "", "removed", "removed"]


def test_without_the_vendor_table_nothing_is_relabelled():
    result = view(entry(4, "tools", "revise", [finding("removed", technique="gpt-3.5-turbo as the model")]))

    assert result["counts"]["statuses"] == {"removed": 1}


def test_a_technique_found_wanting_in_two_chapters_is_one_decision_for_the_course():
    shared = dict(technique="Calculator built on eval()", technique_id="eval-calculator")
    result = view(entry(4, "tools", "revise", [finding("unsafe", **shared)]),
                  entry(4, "agent", "revise", [finding("unsafe", **shared)]),
                  entry(2, "bert", "revise", [finding("missing_context", "Absent", technique_id="absent")]))
    wide = result["course_wide"]

    assert [item["technique_id"] for item in wide] == ["eval-calculator"]
    assert wide[0]["chapters"] == ["C10", "C12"]
    assert wide[0]["act"] == "investigate_larger_change"
    assert "2 notebooks in 2 chapters" in wide[0]["why"]


def test_one_chapter_is_not_course_wide():
    shared = dict(technique="Calculator built on eval()", technique_id="eval-calculator")
    result = view(entry(4, "agent", "revise", [finding("unsafe", **shared)]),
                  entry(4, "agent (1)", "revise", [finding("unsafe", **shared)]))

    assert result["course_wide"] == []


def test_every_notebook_maps_to_one_of_the_brief_actions():
    result = view(entry(4, "tools", "revise", [finding("superseded")]), entry(2, "bert", "keep", []))

    assert book(result, "tools")["act"] == "update_existing_material"
    assert book(result, "bert")["act"] == "watch"


def test_chapters_are_ordered_by_week_then_number_not_as_text():
    result = view(entry(4, "tools", "revise", [finding("superseded")]),
                  entry(4, "agent", "revise", [finding("superseded")]),
                  entry(2, "bert", "revise", [finding("superseded")]))

    assert [chapter["id"] for chapter in result["chapters"]] == ["C4", "C10", "C12"]


def test_every_arabic_sentence_is_built_by_rule_with_latin_digits_and_no_dashes():
    shared = dict(technique="Calculator built on eval()", technique_id="eval-calculator")
    result = view(entry(4, "tools", "replace", [finding("unsafe", **shared), finding("missing_context", "A")]),
                  entry(4, "agent", "revise", [finding("unsafe", **shared)]),
                  entry(4, "agent (1)", "revise", [finding("unsafe", **shared)]),
                  entry(2, "bert", "replace", [finding("missing_context")]))
    sentences = [b["why_ar"] for c in result["chapters"] for b in c["books"]]
    sentences += [item["why_ar"] for item in result["course_wide"]] + [result["basis_ar"]]

    assert all(sentences)
    assert not any(DASH.search(s) or HINDI_DIGIT.search(s) for s in sentences)


def test_reviewer_prose_loses_its_dashes_and_stops_at_a_sentence():
    assert review.clip("Old way — new way", 80) == "Old way, new way"
    assert review.clip("A first sentence ends here. Then more words follow", 40) == "A first sentence ends here."
    assert review.clip("Short. Then a long run of words past the limit", 30) == "Short. Then a long run of…"


def test_no_review_on_this_machine_means_no_material_view(tmp_path):
    assert review.payload(tmp_path / "absent.json") is None


def test_a_file_of_another_shape_is_refused(tmp_path):
    path = tmp_path / "review.json"
    path.write_text(json.dumps({"schema": "something_else/2", "notebooks": []}), encoding="utf-8")

    with pytest.raises(ValueError):
        review.load(path)


def test_the_arabic_tables_cover_every_closed_value():
    assert set(arabic.REVIEW_STATUS) >= set(review.SEVERITY) | {"current"}
    assert set(arabic.REVIEW_VERDICT) == set(review.VERDICTS)
