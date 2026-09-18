import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.schema import Signal

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"


def parse_hn_hit(hit: dict) -> Signal:
    """One Algolia hit -> one Signal. tier=2, source='hackernews', subject=None."""
    object_id = hit["objectID"]
    url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
    published_at = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)

    return Signal(
        id=f"hn_{object_id}",
        source="hackernews",
        tier=2,
        subject=None,
        title=hit["title"],
        url=url,
        published_at=published_at,
    )


def _fetch_page(query: str, page: int) -> dict:
    response = requests.get(
        ALGOLIA_URL,
        params={"query": query, "tags": "story", "hitsPerPage": 20, "page": page},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _save_raw(raw_dir: Path | None, name: str, data: dict) -> None:
    if raw_dir is not None:
        (raw_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def fetch_hackernews(
    queries: list[str], max_pages: int = 3, raw_dir: Path | None = None
) -> tuple[list[dict], list[Signal]]:
    """Returns (raw_responses, signals). Loops queries, pages through results.
    Prints 'TRUNCATED query=<q>' when a query has more pages than max_pages,
    so we can see when we are sampling instead of reading everything.
    If raw_dir is given, each raw page is saved to disk BEFORE it is parsed,
    so a parse crash never loses data that was already fetched."""
    raw_responses: list[dict] = []
    signals: list[Signal] = []
    page_count = 0

    for query in queries:
        data = _fetch_page(query, page=0)
        raw_responses.append(data)
        _save_raw(raw_dir, f"hn_{page_count}", data)
        page_count += 1
        signals.extend(parse_hn_hit(hit) for hit in data["hits"])

        nb_pages = data["nbPages"]
        if nb_pages > max_pages:
            print(f"TRUNCATED query={query}")

        for page in range(1, min(nb_pages, max_pages)):
            data = _fetch_page(query, page=page)
            raw_responses.append(data)
            _save_raw(raw_dir, f"hn_{page_count}", data)
            page_count += 1
            signals.extend(parse_hn_hit(hit) for hit in data["hits"])

    return raw_responses, signals
