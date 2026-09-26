import requests

from src.sources import market


def test_an_employer_names_the_product_not_the_package():
    assert market.job_term("torch") == "pytorch"
    assert market.job_term("llama_index") == "llamaindex"
    assert market.job_term("transformers") == "hugging face"
    assert market.job_term("openai-python") == "openai"


def test_the_langchain_family_is_hired_for_as_one_thing():
    assert market.job_term("langchain-openai") == "langchain"
    assert market.job_term("langgraph-checkpointsqlite") == "langgraph"


def test_nobody_hires_for_a_search_scraper_by_name():
    assert market.job_term("ddgs") is None
    assert market.job_term("mypy-extensions") is None


def test_an_unaliased_package_is_searched_as_itself():
    assert market.job_term("fastapi") == "fastapi"


def test_a_monorepo_subject_maps_to_its_pypi_name():
    assert market.pypi_name("langgraph-checkpointpostgres") == "langgraph-checkpoint-postgres"
    assert market.pypi_name("openai-python") == "openai"
    assert market.pypi_name("fastapi") == "fastapi"


def fake_network(monkeypatch, jobs=None, downloads=None, threads_fail=False, pypi_429_after=None):
    jobs = jobs or {}
    downloads = downloads or {}
    seen = {"pypi": 0}

    monkeypatch.setattr(market.time, "sleep", lambda seconds: None)

    def fake_get(url, params=None, timeout=30):
        if url == market.HN_BY_DATE:
            if threads_fail:
                raise requests.ConnectionError("offline")
            return {"hits": [
                {"objectID": "3", "title": "Ask HN: Who is hiring? (September 2026)"},
                {"objectID": "2", "title": "Ask HN: Who is hiring? (August 2026)"},
                {"objectID": "1", "title": "Ask HN: Who is hiring? (July 2026)"},
            ]}

        if url == market.HN_SEARCH:
            term = params["query"].strip('"')
            return {"nbHits": jobs.get(term, 0)}

        seen["pypi"] += 1

        if pypi_429_after is not None and seen["pypi"] > pypi_429_after:
            response = requests.Response()
            response.status_code = 429
            raise requests.HTTPError(response=response)

        package = url.split("/packages/")[1].split("/")[0]
        return {"data": {"last_month": downloads.get(package, 0)}}

    monkeypatch.setattr(market, "_get", fake_get)
    return seen


def test_job_posts_are_summed_across_the_months(monkeypatch):
    fake_network(monkeypatch, jobs={"langchain": 5})

    result = market.fetch_market(["langchain"], months=3)

    assert result["langchain"]["jobs"] == 15


def test_downloads_are_read_under_the_pypi_name(monkeypatch):
    fake_network(monkeypatch, downloads={"openai": 90_000_000})

    result = market.fetch_market(["openai-python"])

    assert result["openai-python"]["downloads"] == 90_000_000


def test_a_family_is_searched_once_and_shared(monkeypatch):
    queried = []

    def fake_count(term, thread_ids):
        queried.append(term)
        return 7

    fake_network(monkeypatch)
    monkeypatch.setattr(market, "job_posts", fake_count)

    result = market.fetch_market(["langchain", "langchain-core", "langchain-openai"])

    assert queried == ["langchain"]
    assert {entry["jobs"] for entry in result.values()} == {7}


def test_no_hiring_data_is_unmeasured_not_zero(monkeypatch):
    fake_network(monkeypatch, threads_fail=True)

    result = market.fetch_market(["langchain"])

    assert result["langchain"]["jobs"] is None


def test_a_package_nobody_hires_for_has_no_job_count(monkeypatch):
    fake_network(monkeypatch)

    assert market.fetch_market(["ddgs"])["ddgs"]["jobs"] is None


def test_pypistats_that_keeps_refusing_stops_being_asked(monkeypatch):
    seen = fake_network(monkeypatch, downloads={"a": 1, "b": 2}, pypi_429_after=1)

    result = market.fetch_market(["a", "b", "c", "d", "e"])

    assert result["a"]["downloads"] == 1
    assert result["b"]["downloads"] is None
    assert seen["pypi"] == 5


def test_one_rate_limit_is_waited_out_not_taken_as_the_end(monkeypatch):
    import requests as http

    calls = {"n": 0}

    def fake_get(url, params=None, timeout=30):
        if url == market.HN_BY_DATE:
            return {"hits": []}
        calls["n"] += 1
        if calls["n"] == 1:
            response = http.Response()
            response.status_code = 429
            raise http.HTTPError(response=response)
        return {"data": {"last_month": 42}}

    monkeypatch.setattr(market.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(market, "_get", fake_get)

    result = market.fetch_market(["a", "b"])

    assert result["a"]["downloads"] == 42
    assert result["b"]["downloads"] == 42


def test_an_ordinary_english_word_is_not_counted_as_demand():
    assert market.job_term("accelerate") is None
    assert market.job_term("evaluate") is None
    assert market.job_term("requests") is None


def test_the_numbers_are_saved_beside_the_run(tmp_path, monkeypatch):
    import json

    fake_network(monkeypatch, jobs={"fastapi": 8}, downloads={"fastapi": 363_000_000})

    market.fetch_market(["fastapi"], raw_dir=tmp_path)

    saved = json.loads((tmp_path / "market_raw.json").read_text(encoding="utf-8"))

    assert saved["market"]["fastapi"]["jobs"] == 24
    assert len(saved["threads"]) == 3
