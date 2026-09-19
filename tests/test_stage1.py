import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.schema import Signal
from src.sources.hackernews import parse_hn_hit
from src.sources.github_releases import fetch_github_releases, parse_release
from src.stages.stage1_ingest import dedupe_by_url


def load_sample(name):
    return json.loads(Path(f"fixtures/samples/{name}").read_text(encoding="utf-8"))


def test_hn_hit_becomes_signal():
    hit = load_sample("hn_sample.json")["hits"][0]
    s = parse_hn_hit(hit)
    assert s.source == "hackernews"
    assert s.tier == 2
    assert s.published_at.tzinfo is not None   # UTC enforced


def test_hn_hit_without_url_gets_permalink():
    hit = load_sample("hn_sample.json")["hits"][0]
    hit["url"] = None
    s = parse_hn_hit(hit)
    assert "news.ycombinator.com" in s.url


def test_github_release_becomes_signal():
    release = load_sample("github_sample.json")[0]
    s = parse_release("langchain-ai/langgraph", release)
    assert s.source == "github"
    assert s.tier == 1
    assert s.published_at.tzinfo is not None   # UTC enforced


def test_github_monorepo_release_gets_package_subject():
    releases = load_sample("github_sample.json")
    sdk_release = next(r for r in releases if r["tag_name"] == "sdk==0.4.4")
    s = parse_release("langchain-ai/langgraph", sdk_release)
    assert s.subject == "langgraph-sdk"


def test_github_plain_version_release_gets_repo_subject():
    releases = load_sample("github_sample.json")
    core_release = next(r for r in releases if r["tag_name"] == "1.2.11")
    s = parse_release("langchain-ai/langgraph", core_release)
    assert s.subject == "langgraph"


def test_already_qualified_package_is_not_prefixed_twice():
    release = {
        "tag_name": "langchain-core==1.6.3",
        "published_at": "2026-09-16T00:00:00Z",
        "html_url": "https://example.com/r",
        "name": "langchain-core==1.6.3",
        "body": "",
    }

    signal = parse_release("langchain-ai/langchain", release)

    assert signal.subject == "langchain-core"


def _make_signal(id: str, url: str) -> Signal:
    return Signal(
        id=id,
        source="hackernews",
        tier=2,
        title=id,
        url=url,
        published_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )


def test_dedupe_by_url_keeps_one_of_two_matching_urls():
    same_url = "https://news.ycombinator.com/item?id=1"
    signals = [
        _make_signal("hn_1", same_url),
        _make_signal("hn_2", same_url),
    ]

    deduped = dedupe_by_url(signals)

    assert len(deduped) == 1
    assert deduped[0].id == "hn_1"


def test_dedupe_by_url_keeps_signals_with_different_urls():
    signals = [
        _make_signal("hn_1", "https://news.ycombinator.com/item?id=1"),
        _make_signal("hn_2", "https://news.ycombinator.com/item?id=2"),
    ]

    deduped = dedupe_by_url(signals)

    assert len(deduped) == 2


class _FakeResponse:
    def __init__(self, status_code, headers=None, json_data=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data

    def json(self):
        return self._json_data


def test_fetch_github_releases_stops_cleanly_on_403():
    """A 403 (rate limited) on one repo must not crash the whole fetch -
    signals already collected from earlier repos must still come back."""
    ok_release = {
        "tag_name": "1.0.0",
        "published_at": "2026-09-01T00:00:00Z",
        "html_url": "https://example.com/r1",
        "name": "1.0.0",
        "body": "",
    }
    responses = [
        _FakeResponse(200, headers={"X-RateLimit-Remaining": "10"}, json_data=[ok_release]),
        _FakeResponse(403, headers={"X-RateLimit-Remaining": "0"}, json_data={"message": "rate limited"}),
    ]

    with patch("src.sources.github_releases.requests.get", side_effect=responses):
        raw, signals = fetch_github_releases(token=None)

    assert len(raw) == 1
    assert len(signals) == 1
