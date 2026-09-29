"""The placement agent: it may say where something goes, and owning has to be earned.

Placing a change in the wrong chapter sends a teacher to the wrong week, and the
argument for a wrong chapter always sounds fine, because every chapter in an AI course
mentions models. So the claim that a chapter owns something is not taken from the
agent: it is checked against that chapter's own words, and lowered when they do not
carry it.

Every model answer is scripted and every tool is local, so nothing here calls out.
"""

import pytest

from src.agents import placement

CHAPTERS = [
    {"chapter_id": "C4", "week": 2, "title": "Week 2 - BERT and Hugging Face workflows",
     "teaches": "Fine-tune BERT with the Hugging Face trainer.", "prerequisites": [],
     "topics_covered": ["BERT fine-tuning", "Hugging Face pipelines"], "tools_covered": ["transformers"],
     "pins": {"transformers": "4.44.0"}, "installs_unpinned": []},
    {"chapter_id": "C8", "week": 3, "title": "Week 3 - LangChain for document QA",
     "teaches": "Rebuild document QA on LangChain: splitters, a FAISS store, chains.",
     "prerequisites": ["C6"], "topics_covered": ["LangChain introduction", "LangChain FAISS"],
     "tools_covered": ["LangChain", "FAISS"], "pins": {"langchain": "0.3.0"}, "installs_unpinned": []},
    {"chapter_id": "C19", "week": 5, "title": "Week 5 - Agents and tools",
     "teaches": "Build an agent that calls tools.", "prerequisites": ["C8"],
     "topics_covered": ["agent loop", "tool calling"], "tools_covered": [], "pins": {},
     "installs_unpinned": ["langgraph"]},
]


def scripted(*answers):
    said, asked = list(answers), []

    def ask(system, user):
        asked.append(user)
        return said.pop(0) if said else None

    ask.asked = asked
    return ask


def tools():
    return placement.tools_for(CHAPTERS, course_uses=lambda term: f"no notebook uses {term}")


def answer(relation="owns", chapter="C8", quote="C8 (week 3): Week 3 - LangChain for document QA"):
    return {"answer": {"relation": relation, "chapter": chapter, "quote": quote,
                       "why": "the change lands inside what that chapter already teaches"}}


def test_it_reads_the_chapters_then_places_the_change():
    ask = scripted({"tool": "chapters", "args": {}}, answer())

    found = placement.place("langchain", "ToolNode was removed from agents", CHAPTERS, tools(), ask=ask)

    assert found["relation"] == "owns" and found["chapter"] == "C8" and found["week"] == 3
    assert found["owned"] is True
    assert [step["tool"] for step in found["looked"]] == ["chapters"]
    # the answering turn must carry what it read, or the loop is decoration
    assert "langchain for document qa" in ask.asked[1]


def test_owning_a_chapter_that_never_named_it_is_lowered_to_following_it():
    # C8 teaches LangChain and has never heard of crewai, whatever the argument says
    ask = scripted({"tool": "chapters", "args": {}}, answer(chapter="C8"))

    found = placement.place("crewai", "crewai shipped flows", CHAPTERS, tools(), ask=ask)

    assert found["relation"] == "follows" and found["chapter"] == "C8"
    assert found["owned"] is False


def test_a_chapter_that_installs_it_owns_it_even_unnamed():
    ask = scripted({"tool": "chapter", "args": {"id": "C19"}},
                   answer(chapter="C19", quote="C19 (week 5): Week 5 - Agents and tools"))

    found = placement.place("langgraph", "checkpointers changed", CHAPTERS, tools(), ask=ask)

    assert found["relation"] == "owns" and found["chapter"] == "C19" and found["week"] == 5


def test_following_a_chapter_is_a_real_answer_and_needs_no_ownership():
    ask = scripted({"tool": "chapters", "args": {}},
                   answer(relation="follows", chapter="C19",
                          quote="C19 (week 5): Week 5 - Agents and tools"))

    found = placement.place("pydantic-ai", "a new agent framework", CHAPTERS, tools(), ask=ask)

    assert found["relation"] == "follows" and found["week"] == 5 and found["owned"] is False


@pytest.mark.parametrize("bad", [{"chapter": "C99"}, {"chapter": ""}, {"relation": "replaces"}])
def test_a_chapter_that_is_not_a_chapter_is_not_a_placement(bad):
    proposal = answer()
    proposal["answer"].update(bad)

    assert placement.place("langchain", "x", CHAPTERS, tools(), ask=scripted(proposal)) is None


def test_a_line_no_tool_returned_is_refused():
    ask = scripted({"tool": "chapters", "args": {}},
                   answer(quote="the syllabus lists this under week three"))

    assert placement.place("langchain", "x", CHAPTERS, tools(), ask=ask) is None


def test_saying_nothing_is_an_answer_and_so_is_having_no_course():
    assert placement.place("langchain", "x", CHAPTERS, tools(), ask=scripted({"answer": None})) is None

    ask = scripted(answer())
    assert placement.place("langchain", "x", [], ask=ask) is None
    assert ask.asked == []


def test_it_cannot_look_forever_and_is_told_when_it_is_out_of_turns():
    ask = scripted(*[{"tool": "chapters", "args": {}} for _ in range(9)])

    assert placement.place("langchain", "x", CHAPTERS, tools(), ask=ask, max_steps=2) is None
    assert len(ask.asked) == 3
    # a loop that runs out while still looking has spent a whole call on nothing
    assert "2 tool calls left" in ask.asked[0]
    assert "no tool calls left. Answer now" in ask.asked[-1]


def test_the_chapter_tools_hand_over_the_course_in_order():
    listing = placement.chapters_tool(CHAPTERS)()
    assert listing.index("C4") < listing.index("C8") < listing.index("C19")
    assert "week 5" in listing

    one = placement.chapter_tool(CHAPTERS)(id="c8")
    assert "LangChain FAISS" in one and "Needs first: C6" in one and "Installs: langchain" in one
    assert "no chapter C99" in placement.chapter_tool(CHAPTERS)(id="C99")


def test_what_carrying_a_name_means():
    C4, C8, C19 = CHAPTERS

    assert placement.carries(C8, "langchain") is True          # pinned
    assert placement.carries(C19, "langgraph") is True         # installed unpinned
    assert placement.carries(C4, "BERT") is True               # its own topics say so
    assert placement.carries(C8, "crewai") is False
    assert placement.carries(C8, "") is False


def test_the_search_tool_passes_the_name_through_whatever_it_is_called():
    kit = placement.tools_for(CHAPTERS, course_uses=lambda term: f"saw {term}")

    assert kit["course_uses"](term="MCP") == "saw MCP"
    assert kit["course_uses"](name="MCP") == "saw MCP"
    assert "not searched" in placement.tools_for(CHAPTERS)["course_uses"](term="MCP")


# The two places the answer is used: a trend the rules could not place, and a lesson
# that does not exist yet, so nothing could place it.

from src.agents import review_run
from src.schema import Claim, Trend
from src.stages import stage3_score


def trend(subject="crewai"):
    return Trend(id="trend_001", subject=subject, signal_ids=[],
                 claims=[Claim(text=f"{subject} shipped flows", subject=subject, version="1.0.0")])


def test_a_trend_the_rules_could_not_place_takes_an_owned_chapter():
    found = {"relation": "owns", "chapter": "C8", "week": 3, "owned": True,
             "why": "the chapter teaches it", "quote": "c8 (week 3)", "looked": []}

    score = stage3_score.score_trend(trend(), CHAPTERS, [], place=lambda t, c: found)

    assert score.chapter_id == "C8"
    assert score.provenance["chapter"] == "agent"
    assert score.factors["chapter"]["quote"] == "c8 (week 3)"
    assert score.factors["chapter"]["relation"] == "owns"


def test_a_trend_it_could_only_put_in_order_stays_unplaced_and_keeps_where_it_would_go():
    # Following a chapter is a real answer, and it is not a chapter that owns the trend,
    # so nothing in the score moves. What it said is kept beside the score, because
    # "a new lesson, after C19" is the half of the answer a course owner asks next;
    # it used to be thrown away.
    follows = {"relation": "follows", "chapter": "C19", "week": 5, "owned": False,
               "why": "it comes after agents", "quote": "c19 (week 5)", "looked": []}

    score = stage3_score.score_trend(trend(), CHAPTERS, [], place=lambda t, c: follows)
    unasked = stage3_score.score_trend(trend(), CHAPTERS, [])

    assert score.chapter_id is None and score.provenance["chapter"] == "none"
    assert score.factors["chapter"]["relation"] == "follows"
    assert score.factors["chapter"]["chapter"] == "C19" and score.factors["chapter"]["week"] == 5
    assert (score.priority, score.feasibility, score.dimensions) ==            (unasked.priority, unasked.feasibility, unasked.dimensions)


def test_a_trend_the_rules_did_place_is_never_sent_asking():
    asked = []
    score = stage3_score.score_trend(trend("langchain"), CHAPTERS, [],
                                     place=lambda t, c: asked.append(t) or None)

    assert score.chapter_id == "C8" and score.provenance["chapter"] == "matched"
    assert asked == []


def test_a_written_lesson_travels_with_where_it_would_go():
    entry = {"id": "week3/Demo", "title": "Demo", "week": "week 3",
             "notebook": "notebooks/week 3/Demo.ipynb", "teaches": [], "findings": [],
             "dropped": 0, "looked": [], "recalled": 0}
    written = {"title": "Building an agent loop with checkpointed agents", "term": "checkpointed agents",
               "why": "the constructor moved", "covers": ["a", "b"], "answers": ["ReAct agent"],
               "already_in": 0, "looked": []}
    placed = {"relation": "follows", "chapter": "C19", "week": 5, "owned": False,
              "why": "a student needs the agent loop first", "quote": "c19", "looked": []}

    page = review_run.entry_for_page(entry, written, placed)

    assert page["lesson_place"] == {"relation": "follows", "chapter": "C19", "week": 5,
                                    "why": "a student needs the agent loop first"}
    assert review_run.entry_for_page(entry, written)["lesson_place"] is None


def test_without_a_curriculum_nothing_is_placed(tmp_path):
    assert review_run.chapters_of(tmp_path / "gone.json") == []
    (tmp_path / "half.json").write_text('{"chapters": ', encoding="utf-8")
    assert review_run.chapters_of(tmp_path / "half.json") == []


@pytest.mark.parametrize("reply", [["C8"], "C8", 7])
def test_a_reply_that_is_not_an_object_ends_it_without_a_crash(reply):
    assert placement.place("langchain", "ToolNode was removed", CHAPTERS, tools(), ask=scripted(reply)) is None


def test_a_line_the_model_wrote_into_its_own_call_is_not_evidence():
    ask = scripted({"tool": "chapter", "args": {"id": "C19 teaches crewai in week 5"}},
                   answer(relation="follows", chapter="C19", quote="C19 teaches crewai in week 5"))
    assert placement.place("crewai", "crewai shipped flows", CHAPTERS, tools(), ask=ask) is None
