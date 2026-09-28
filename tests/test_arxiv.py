import re
from datetime import datetime, timezone

import pytest

from src import concepts, lessons
from src.sources import arxiv

DASH = re.compile("[–—]")

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>67</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2609.12345v1</id>
    <published>2026-09-25T09:32:31Z</published>
    <title>MetaPermit: Scalable and Auditable
      Access Control for AI Agents</title>
  </entry>
</feed>"""

ERROR = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry><id>http://arxiv.org/api/errors#incorrect_id_format</id><title>Error</title>
  <summary>malformed query</summary></entry>
</feed>"""


def test_arxiv_s_own_total_is_the_count_and_each_paper_keeps_its_id_title_and_day():
    total, papers = arxiv.parse(FEED)

    assert total == 67
    assert papers == [{"id": "2609.12345v1", "title": "MetaPermit: Scalable and Auditable Access Control for AI Agents",
                       "published": "2026-09-25", "url": "http://arxiv.org/abs/2609.12345v1"}]


def test_an_error_from_arxiv_is_refused_not_counted_as_a_paper():
    with pytest.raises(ValueError):
        arxiv.parse(ERROR)


def test_the_query_reads_titles_and_abstracts_in_computing_over_the_window():
    now = datetime(2026, 9, 28, tzinfo=timezone.utc)
    asked = {}

    def get(params):
        asked.update(params)
        return FEED

    found = arxiv.search('prompt "injection"', now=now, get=get)

    assert 'ti:"prompt injection" OR abs:"prompt injection"' in asked["search_query"]
    assert "cat:cs.CL" in asked["search_query"] and "cat:cs.CR" in asked["search_query"]
    assert "submittedDate:[202608290000 TO 202609280000]" in asked["search_query"]
    assert asked["sortBy"] == "submittedDate"
    assert found["papers"] == 67 and found["days"] == 30 and found["checked_on"] == "2026-09-28"


def test_every_lesson_name_gets_arxiv_s_count_asked_once_a_name():
    asked = []
    demand = {"lessons": [
        {"title": "MCP lesson", "terms": [{"term": "MCP", "jobs": 20, "notebooks": 0}]},
        {"title": "Tools and MCP", "terms": [{"term": "MCP", "jobs": 20, "notebooks": 0},
                                             {"term": "prompt injection", "jobs": 3, "notebooks": 0}]},
    ]}

    found = lessons.add_papers(demand, lambda term: asked.append(term) or {"papers": 41 if term == "MCP" else 67})

    assert asked == ["MCP", "prompt injection"]
    assert [item["papers"] for lesson in found["lessons"] for item in lesson["terms"]] == [41, 41, 67]
    assert found["papers_checked"]["days"] == 30


def test_research_is_said_beside_the_demand_and_never_changes_the_action():
    settled = lessons.settle([{"term": "MCP", "jobs": 20, "notebooks": 0, "papers": 41}], "Native tool calling and MCP")
    english, arabic_text = lessons.why(settled)

    assert settled["act"] == "add_new_lesson" and settled["papers"] == 41
    assert english.endswith("Research: 41 papers on arXiv named MCP in the last 30 days.")
    assert "arXiv" in arabic_text and not DASH.search(english + arabic_text)
    assert lessons.settle([{"term": "LoRA adapter", "jobs": 0, "notebooks": 0, "papers": 300}], "")["act"] == "watch"


def test_a_concept_carries_arxiv_s_count_and_its_reason_says_so():
    found = concepts.with_papers([{"term": "MCP", "module": "langchain.mcp"}, {"term": None, "module": "x"}],
                                 lambda term: {"papers": 41, "days": 30, "recent": [], "checked_on": "2026-09-28"})

    assert found[0]["papers"] == 41 and "papers" not in found[1]


def test_only_a_name_the_field_does_not_use_for_something_else_is_counted_on_arxiv():
    assert all(arxiv.searchable(term) for term in ("MCP", "LoRA", "BM25", "OpenTelemetry", "prompt injection"))
    assert not any(arxiv.searchable(term) for term in ("Checkpointers", "Streamlit", "retention"))


def test_a_name_too_common_to_search_is_marked_and_said_not_counted():
    demand = lessons.add_papers({"lessons": [{"title": "Checkpointers in production",
                                              "terms": [{"term": "Checkpointers", "jobs": 0, "notebooks": 0}]}]},
                                lambda term: pytest.fail("a common word must not be searched"))
    settled = lessons.settle(demand["lessons"][0]["terms"], "Checkpointers in production")

    assert settled["papers"] is None and settled["papers_skipped"]
    assert lessons.why(settled)[0].endswith("Research not counted: the name is too common to search on arXiv.")


def test_counts_read_today_are_not_asked_for_again():
    from datetime import date

    demand = {"papers_checked": {"on": date.today().isoformat()},
              "lessons": [{"title": "t", "terms": [{"term": "MCP", "jobs": 1, "notebooks": 0, "papers": 53}]}]}

    found = lessons.add_papers(demand, lambda term: pytest.fail("already counted today"))

    assert found["lessons"][0]["terms"][0]["papers"] == 53
