import json
from pathlib import Path

from src.sources.hackernews import parse_hn_hit
from src.sources.github_releases import parse_release


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
