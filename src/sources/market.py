"""Whether the market wants a tool, measured two ways.

Employer demand comes from Hacker News' monthly "Ask HN: Who is hiring?" threads:
real companies, posting real roles, several hundred a month. We count the posts
that name each tool, over the last few months so one quiet month does not read as
a collapse.

Adoption comes from PyPI download counts: how many installs a package had last
month. It answers a different question - how widely a tool is used, not how often
someone is paid to use it - and the two are kept apart rather than blended into a
single number that hides which one moved.

Both are network calls, so they run at collection time and are saved beside the
run. A replay reads the saved numbers and never touches the network.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import requests

HN_SEARCH = "https://hn.algolia.com/api/v1/search"
HN_BY_DATE = "https://hn.algolia.com/api/v1/search_by_date"
PYPISTATS = "https://pypistats.org/api/packages/{}/recent"
HEADERS = {"User-Agent": "ai-trend-agent/1.0 (SDA bootcamp capstone)"}
MAX_BACKOFF = 20.0

# What an employer writes in a job post, which is rarely the package name.
JOB_TERMS = {
    "openai-python": "openai", "openai": "openai",
    "anthropic-sdk-python": "anthropic", "anthropic": "anthropic",
    "llama_index": "llamaindex", "llama-index": "llamaindex",
    "torch": "pytorch", "torchvision": "pytorch", "torchaudio": "pytorch",
    "transformers": "hugging face",
    "faiss-cpu": "faiss", "faiss-gpu-cu12": "faiss",
    "pydantic-ai": "pydantic",
    "sentence-transformers": "sentence-transformers",
    "scikit-learn": "scikit-learn",
    "beautifulsoup4": "beautifulsoup",
    "duckduckgo-search": None, "ddgs": None, "google-search-results": None,
    "google-serp-api": None, "mypy-extensions": None, "ipykernel": None,
    "langchainhub": None,
    # Ordinary English words. "accelerate" matched 22 posts in three months,
    # most of them asking someone to accelerate a roadmap; a count we cannot
    # tell apart from noise is left unmeasured rather than reported.
    "accelerate": None, "evaluate": None, "requests": None, "datasets": None,
    "unstructured": None, "evidently": None, "tenacity": None, "wikipedia": None,
}

# Where a subject collected from a GitHub monorepo tag has a different PyPI name.
PYPI_NAMES = {
    "openai-python": "openai",
    "anthropic-sdk-python": "anthropic",
    "llama_index": "llama-index",
    "langgraph-checkpointpostgres": "langgraph-checkpoint-postgres",
    "langgraph-checkpointsqlite": "langgraph-checkpoint-sqlite",
}


def job_term(subject: str) -> str | None:
    """The word to look for in job posts, or None when no one hires for it by name."""
    if subject in JOB_TERMS:
        return JOB_TERMS[subject]

    for family in ("langchain", "langgraph"):
        if subject.startswith(family):
            return family

    return subject


def pypi_name(subject: str) -> str:
    return PYPI_NAMES.get(subject, subject)


def _get(url: str, params: dict | None = None, timeout: int = 30) -> dict:
    target = f"{url}?{urlencode(params)}" if params else url
    response = requests.get(target, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.json()


def hiring_threads(months: int = 3) -> list[dict]:
    """The latest monthly hiring threads, newest first."""
    data = _get(HN_BY_DATE, {
        "query": "Ask HN: Who is hiring?", "tags": "story,author_whoishiring",
        "hitsPerPage": months + 3,
    })
    threads = [hit for hit in data.get("hits", []) if "who is hiring" in hit.get("title", "").lower()]

    return [{"id": hit["objectID"], "title": hit["title"]} for hit in threads[:months]]


def job_posts(term: str, thread_ids: list[str]) -> int:
    """Job posts naming the term, across the given threads.

    Exact word, no typo tolerance: without both, "rag" matched 97 posts in one
    month, most of them "storage" and "leverage".
    """
    total = 0

    for thread_id in thread_ids:
        data = _get(HN_SEARCH, {
            "query": f'"{term}"', "tags": f"comment,story_{thread_id}",
            "hitsPerPage": 0, "typoTolerance": "false",
        })
        total += int(data.get("nbHits", 0))

    return total


def monthly_downloads(package: str) -> int | None:
    data = _get(PYPISTATS.format(package))

    return (data.get("data") or {}).get("last_month")


def fetch_market(subjects: list[str], months: int = 3, raw_dir: Path | None = None,
                 workers: int = 6) -> dict[str, dict]:
    """Job demand and adoption for each subject.

    Never raises. A source that fails leaves its numbers as None, which the
    scorer treats as unmeasured rather than as zero; zero would mean "nobody
    wants this", which we would not know.
    """
    market = {subject: {"jobs": None, "job_term": job_term(subject), "downloads": None,
                        "months": months} for subject in subjects}

    try:
        threads = hiring_threads(months)
    except (requests.RequestException, ValueError) as problem:
        threads = []
        print(f"market: hiring threads unavailable ({type(problem).__name__})")

    thread_ids = [thread["id"] for thread in threads]
    terms = sorted({entry["job_term"] for entry in market.values() if entry["job_term"]})
    counts: dict[str, int | None] = {}

    def count(term: str) -> tuple[str, int | None]:
        try:
            return term, job_posts(term, thread_ids)
        except (requests.RequestException, ValueError):
            return term, None

    if thread_ids:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            counts = dict(pool.map(count, terms))

    for entry in market.values():
        if entry["job_term"] and thread_ids:
            entry["jobs"] = counts.get(entry["job_term"])

    # pypistats asks to be treated gently: one at a time. A 429 means wait, not
    # stop - stopping on the first one cost a run every download count, when a
    # few seconds later it was answering again. Two refusals in a row, and we
    # leave the rest unmeasured rather than hammer it.
    refused_in_a_row = 0

    for subject in subjects:
        if refused_in_a_row >= 2:
            break

        for attempt in range(2):
            try:
                market[subject]["downloads"] = monthly_downloads(pypi_name(subject))
                refused_in_a_row = 0
                break
            except requests.HTTPError as problem:
                limited = problem.response is not None and problem.response.status_code == 429

                if not limited:
                    break

                if attempt == 0:
                    retry_after = problem.response.headers.get("Retry-After") if problem.response is not None else None
                    time.sleep(min(float(retry_after or 5), MAX_BACKOFF))
                    continue

                refused_in_a_row += 1
            except (requests.RequestException, ValueError):
                break

        time.sleep(0.25)

    if refused_in_a_row >= 2:
        print("market: pypistats kept refusing, the rest of adoption is unmeasured")

    if raw_dir is not None:
        (raw_dir / "market_raw.json").write_text(json.dumps({"threads": threads, "market": market}),
                                             encoding="utf-8")

    measured_jobs = sum(1 for entry in market.values() if entry["jobs"] is not None)
    measured_downloads = sum(1 for entry in market.values() if entry["downloads"] is not None)
    print(f"market: {len(threads)} hiring threads, jobs for {measured_jobs}, "
          f"downloads for {measured_downloads} of {len(subjects)} subjects")

    return market
