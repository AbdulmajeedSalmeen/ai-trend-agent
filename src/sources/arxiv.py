"""Research, from arXiv: how many new papers name a term, and the newest of them.

arXiv is the primary record of a paper: its id, its title and the day it was
submitted are arXiv's own, read through its public API. A count of papers is
research activity, not demand. Employers decide whether a lesson is worth
teaching; papers only say where the field is moving, so the count is shown beside
the job posts and never decides an action. arXiv asks for no more than one
request every three seconds, so every call waits its turn.
"""
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

API = "https://export.arxiv.org/api/query"
HEADERS = {"User-Agent": "ai-trend-agent/1.0 (SDA bootcamp capstone)"}
NS = {"a": "http://www.w3.org/2005/Atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}
PAUSE = 3.0
DAYS = 30
# Where papers about building LLM and agent systems are filed. A term like MCP
# also names things in physics and medicine; the categories keep those out.
CATEGORIES = ("cs.CL", "cs.AI", "cs.LG", "cs.IR", "cs.CR", "cs.SE", "cs.MA")

_last_call = [0.0]


def searchable(term: str) -> bool:
    """Whether arXiv's count for a name would be about the name. A phrase is searched
    whole. One word has to be a name the field does not use for something else: an
    acronym or a coined name with a capital or digit inside it (MCP, LoRA, BM25,
    OpenTelemetry). "Checkpointers" found 245 papers, nearly all of them about saving
    training checkpoints, not an agent's saved state."""
    term = term.strip()

    if " " in term:
        return True

    return any(character.isupper() or character.isdigit() for character in term[1:])


def query(term: str, start: datetime, end: datetime) -> str:
    phrase = term.replace('"', "").strip()
    categories = " OR ".join(f"cat:{category}" for category in CATEGORIES)
    return (f'(ti:"{phrase}" OR abs:"{phrase}") AND ({categories}) '
            f"AND submittedDate:[{start:%Y%m%d%H%M} TO {end:%Y%m%d%H%M}]")


def parse(text: str) -> tuple[int, list[dict]]:
    """The total arXiv reports for the query, and the papers it returned. arXiv
    answers a malformed query with a single entry titled Error, which is refused
    rather than counted as a paper."""
    root = ET.fromstring(text)
    papers = []

    for entry in root.findall("a:entry", NS):
        link = (entry.findtext("a:id", default="", namespaces=NS) or "").strip()

        if "/api/errors" in link:
            raise ValueError(f"arXiv refused the query: {entry.findtext('a:summary', default='', namespaces=NS)}")

        papers.append({
            "id": link.rsplit("/abs/", 1)[-1],
            "title": " ".join((entry.findtext("a:title", default="", namespaces=NS) or "").split()),
            "published": (entry.findtext("a:published", default="", namespaces=NS) or "")[:10],
            "url": link,
        })

    return int(root.findtext("os:totalResults", default="0", namespaces=NS) or 0), papers


def polite_get(params: dict) -> str:
    wait = PAUSE - (time.monotonic() - _last_call[0])

    if wait > 0:
        time.sleep(wait)

    try:
        response = requests.get(API, params=params, headers=HEADERS, timeout=30)
    finally:
        _last_call[0] = time.monotonic()

    response.raise_for_status()
    return response.text


def search(term: str, days: int = DAYS, now: datetime | None = None, recent: int = 3, get=polite_get) -> dict:
    """Papers submitted in the last `days` that name the term in their title or
    abstract: how many, and the newest few."""
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    total, papers = parse(get({"search_query": query(term, start, end), "max_results": recent,
                               "sortBy": "submittedDate", "sortOrder": "descending"}))
    return {"term": term, "papers": total, "days": days, "recent": papers, "checked_on": end.date().isoformat()}
