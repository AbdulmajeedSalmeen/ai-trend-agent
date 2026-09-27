import re

from src import lessons, review

DASH = re.compile("[–—]")

MCP = {"notebook": "notebooks/week 4/tools.ipynb", "id": "week4/tools", "title": "Native tool calling and MCP",
       "covers": ["MCP: exposing the same tools as a server", "parallel tool calls in one turn"]}
INJECTION = {"notebook": "notebooks/week 4/agent.ipynb", "id": "week4/agent",
             "title": "Untrusted tool output: prompt injection", "covers": ["OWASP LLM01 indirect injection"]}
STREAMLIT = {"notebook": "notebooks/week 3/app.ipynb", "id": "week3/app", "title": "Ship the agent as a Streamlit app",
             "covers": ["st.chat_input as the app shell"]}


def answers(terms):
    return lambda system, user: {"terms": terms}


def test_a_term_must_be_written_in_the_lesson_itself():
    assert lessons.valid("prompt injection", INJECTION)
    assert lessons.valid("MCP", MCP)
    assert not lessons.valid("LangGraph", MCP)


def test_a_word_every_ai_job_post_carries_is_not_a_term():
    lesson = {"title": "Evaluate the LLM agent in Python", "covers": []}

    assert not any(lessons.valid(term, lesson) for term in ("LLM", "agent", "Python"))


def test_a_term_is_a_name_not_a_sentence():
    assert not lessons.valid("Native tool calling and MCP", MCP)


def test_the_model_picks_and_the_rules_keep_only_what_passes():
    picked = lessons.pick_terms([MCP, INJECTION], answers({"1": ["MCP", "LangGraph", "mcp"],
                                                          "2": ["prompt injection", "AI"]}))

    assert picked == {MCP["notebook"]: ["MCP"], INJECTION["notebook"]: ["prompt injection"]}


def test_no_model_means_no_terms_and_nothing_promoted():
    picked = lessons.pick_terms([MCP], lambda system, user: None)
    found = lessons.measure([MCP], picked, lambda term: 99, [])

    assert picked == {MCP["notebook"]: []}
    assert found[0]["act"] == "watch" and found[0]["jobs"] is None


def test_demand_decides_the_action_the_way_it_does_for_a_concept():
    assert lessons.decide(None, 0) == "watch"
    assert lessons.decide(0, 0) == "watch"
    assert lessons.decide(20, 0) == "add_new_lesson"
    assert lessons.decide(2, 0) == "add_optional_content"
    assert lessons.decide(20, 3) == "add_optional_content"


def test_the_name_employers_ask_for_most_speaks_for_the_lesson():
    counts = {"MCP": 20, "parallel tool calls": 1}
    found = lessons.measure([MCP], {MCP["notebook"]: ["parallel tool calls", "MCP"]}, counts.get,
                            ["a notebook about tools", "another one"])

    assert found[0]["term"] == "MCP" and found[0]["jobs"] == 20
    assert found[0]["act"] == "add_new_lesson"


def test_a_lesson_on_something_the_course_already_names_is_optional_at_most():
    found = lessons.measure([STREAMLIT], {STREAMLIT["notebook"]: ["Streamlit"]}, lambda term: 12,
                            ["import streamlit as st  # Streamlit demo"])

    assert found[0]["mentioned"] == 1
    assert found[0]["act"] == "add_optional_content"


def test_a_copy_does_not_propose_its_lesson_twice():
    material = {"notebooks": [
        {"notebook": "notebooks/week 5/x.ipynb", "id": "week5/x", "new_lesson": {"title": "T", "covers": []}},
        {"notebook": "notebooks/week 5/x (1).ipynb", "id": "week5/x (1)", "new_lesson": {"title": "T", "covers": []}},
    ]}

    assert [lesson["id"] for lesson in lessons.proposals(material, {"notebooks/week 5/x (1).ipynb"})] == ["week5/x"]


def test_every_reason_is_in_both_languages_with_no_dashes():
    cases = [
        {"term": None, "jobs": None, "mentioned": 0, "act": "watch"},
        {"term": "MCP", "jobs": 0, "mentioned": 0, "act": "watch"},
        {"term": "MCP", "jobs": 20, "mentioned": 0, "act": "add_new_lesson"},
        {"term": "prompt injection", "jobs": 2, "mentioned": 0, "act": "add_optional_content"},
        {"term": "Streamlit", "jobs": 12, "mentioned": 2, "act": "add_optional_content"},
    ]

    for case in cases:
        english, arabic_text = lessons.why(case)
        assert english and arabic_text
        assert not DASH.search(english + arabic_text)

    assert lessons.why(cases[2])[0] == "20 job posts named MCP in the last 3 months, and no notebook names it: a new lesson."


def test_the_material_view_carries_each_measured_lesson_and_counts_them():
    material = {"schema": review.SCHEMA, "read_on": "2026-09-26", "notebooks": [
        {"id": "week4/tools", "notebook": "notebooks/week 4/tools.ipynb", "week_number": 4, "verdict": "revise",
         "findings": [{"technique": "Dispatcher", "status": "superseded", "cell": 3}],
         "new_lesson": {"title": "Native tool calling and MCP", "covers": []}},
    ]}
    curriculum = {"chapters": [{"chapter_id": "C12", "week": 4, "title": "Week 4 - Tools",
                                "notebooks": ["tools.ipynb"], "material_edits": []}]}
    demand = {"checked_on": "2026-09-26", "months": 3, "picked_by": "groq", "lessons": [
        {"notebook": "notebooks/week 4/tools.ipynb", "title": "Native tool calling and MCP",
         "terms": [{"term": "MCP", "jobs": 20, "notebooks": 0}]}]}

    view = review.build(material, curriculum, [], None, demand)

    assert view["lessons"][0]["term"] == "MCP" and view["lessons"][0]["act"] == "add_new_lesson"
    assert view["counts"]["lessons_new"] == 1 and view["counts"]["lessons_measured"] == 1
    assert view["chapters"][0]["books"][0]["ld"]["why_ar"]
    assert view["lessons_checked"]["picked_by"] == "groq"


def test_without_a_demand_file_the_view_has_no_lessons_and_says_so():
    material = {"schema": review.SCHEMA, "read_on": "2026-09-26", "notebooks": []}

    view = review.build(material, {"chapters": []}, [], None)

    assert view["lessons"] == [] and view["lessons_checked"] is None


def test_one_ordinary_word_is_not_a_name():
    lesson = {"title": "Writing memory well", "covers": ["retention, deletion and the right to be forgotten"]}

    assert not lessons.valid("retention", lesson)


def test_code_is_not_a_job_post_word():
    lesson = {"title": "Tracing agents", "covers": ["gen_ai.* spans", "recall@k and MRR", "st.secrets"]}

    assert not any(lessons.valid(term, lesson) for term in ("gen_ai.* spans", "recall@k", "st.secrets"))
    assert lessons.valid("MRR", lesson)


def test_what_the_lesson_adds_speaks_before_what_it_builds_on():
    lesson = {"notebook": "n", "id": "i", "title": "Multi-agent with LangChain and LangSmith", "covers": []}
    counts = {"LangChain": 17, "LangSmith": 2}
    found = lessons.measure([lesson], {"n": ["LangChain", "LangSmith"]}, counts.get,
                            ["from langchain import hub  # LangChain"])

    assert found[0]["term"] == "LangSmith" and found[0]["mentioned"] == 0


def test_a_name_the_course_already_teaches_cannot_speak_for_a_lesson_that_offered_a_new_one():
    settled = lessons.settle([{"term": "LangChain", "jobs": 17, "notebooks": 40},
                              {"term": "MAST", "jobs": 0, "notebooks": 0}])

    assert settled["term"] == "MAST" and settled["act"] == "watch"


def test_a_taught_name_speaks_only_when_it_is_the_lesson_s_subject():
    terms = [{"term": "multi-agent system", "jobs": 0, "notebooks": 9},
             {"term": "LangChain", "jobs": 17, "notebooks": 64}]

    assert lessons.settle(terms, "When not to build a multi-agent system")["term"] == "multi-agent system"
    assert lessons.settle([{"term": "Streamlit", "jobs": 3, "notebooks": 1}],
                          "Ship the agent as a Streamlit app")["act"] == "add_optional_content"
    assert lessons.settle([{"term": "LangChain", "jobs": 17, "notebooks": 64}], "Budgets for agent loops")["act"] == "watch"


def test_the_decision_is_remade_from_the_saved_counts_when_the_page_is_built():
    view = review.lesson_view({"title": "Tracing with LangSmith", "term": "LangChain", "act": "add_optional_content",
                               "terms": [{"term": "LangChain", "jobs": 17, "notebooks": 40},
                                         {"term": "LangSmith", "jobs": 2, "notebooks": 0}]}, 3)

    assert view["term"] == "LangSmith" and view["act"] == "add_optional_content"
    assert view["why"].startswith("2 job posts named LangSmith")
