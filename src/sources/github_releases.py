import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.schema import Signal

GITHUB_API = "https://api.github.com/repos"
PER_PAGE = 100
MAX_PAGES = 3

WATCHLIST = [
    "langchain-ai/langgraph",
    "langchain-ai/langchain",
    "huggingface/transformers",
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "pydantic/pydantic-ai",
    "crewAIInc/crewAI",
    "run-llama/llama_index",
]


def parse_release(repo: str, release: dict) -> Signal:
    """tier=1, source='github'.
    subject comes from the repo name after the slash, lowercased, EXCEPT when the
    repo holds several packages (monorepo). Check tag_name:
      'sdk==0.4.4'  -> subject 'langgraph-sdk'  (part before '==' joined to repo name)
      '1.2.11'      -> subject 'langgraph'      (plain version = the main package)
    Without this, a claim about langgraph 4.2.0 gets confirmed by checkpoint==4.2.0.
    id = 'gh_<subject>_<tag_name>'. published_at: datetime.fromisoformat works on
    GitHub's format after replacing the trailing 'Z' with '+00:00'."""
    tag_name = release["tag_name"]
    repo_name = repo.split("/")[-1].lower()
    subject = repo_name

    if "==" in tag_name:
        package, _, _version = tag_name.partition("==")
        package = package.lower()
        if package.startswith(repo_name):
            subject = package
        else:
            subject = f"{repo_name}-{package}"

    published_at = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))

    return Signal(
        id=f"gh_{subject}_{tag_name}",
        source="github",
        tier=1,
        subject=subject,
        title=release.get("name") or tag_name,
        url=release["html_url"],
        published_at=published_at,
        body=release.get("body") or "",
    )


def published(release: dict) -> datetime | None:
    stamp = release.get("published_at")
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None


def fetch_github_releases(
    token: str | None, raw_dir: Path | None = None, days: int = 30, now: datetime | None = None
) -> tuple[list[dict], list[Signal]]:
    """Every release of each watched repo published in the last `days`.

    A fixed count per repo used to be read instead: the last 10. That gave every
    run exactly 80 signals, and gave each repo a different span of time, nine
    days of openai-python against six months of llama_index, while PyPI read a
    30-day window. A window reads the same stretch of time for every repo, and a
    monorepo such as langchain-ai/langchain, which ships a dozen packages, is
    read in full rather than cut at its tenth release.

    Pages are read newest first until one reaches past the window. A 403 (rate
    limited or forbidden) stops the loop and returns what was already collected:
    partial data beats a crash. Stops early, with a warning, when fewer than 5
    requests remain. If raw_dir is given, each repo's releases are saved before
    they are parsed, so a parse crash never loses data already fetched."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    raw_responses: list[dict] = []
    signals: list[Signal] = []
    stopped = False

    for i, repo in enumerate(WATCHLIST):
        in_window = []
        remaining = None

        for page in range(1, MAX_PAGES + 1):
            response = requests.get(
                f"{GITHUB_API}/{repo}/releases",
                params={"per_page": PER_PAGE, "page": page},
                headers=headers,
                timeout=30,
            )
            remaining = response.headers.get("X-RateLimit-Remaining")
            print(f"{repo}: X-RateLimit-Remaining={remaining}")

            if response.status_code == 403:
                print(f"WARNING: {repo} returned 403 (rate limited or forbidden), stopping early")
                stopped = True
                break

            releases = response.json()
            fresh = [release for release in releases
                     if published(release) is not None and published(release) >= since]
            in_window.extend(fresh)

            if len(fresh) < len(releases) or len(releases) < PER_PAGE:
                break

        if stopped and not in_window:
            break

        entry = {"repo": repo, "since": since.isoformat(), "releases": in_window}
        raw_responses.append(entry)
        if raw_dir is not None:
            (raw_dir / f"github_{i}.json").write_text(json.dumps(entry), encoding="utf-8")

        signals.extend(parse_release(repo, release) for release in in_window)

        if stopped:
            break

        if remaining is not None and int(remaining) < 5:
            print(f"WARNING: GitHub rate limit low ({remaining} remaining), stopping")
            break

    return raw_responses, signals
