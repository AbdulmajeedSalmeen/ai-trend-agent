import json
from datetime import datetime
from pathlib import Path

import requests

from src.schema import Signal

GITHUB_API = "https://api.github.com/repos"

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


def fetch_github_releases(
    token: str | None, raw_dir: Path | None = None
) -> tuple[list[dict], list[Signal]]:
    """Header: {'Authorization': f'Bearer {token}'} if token else {}.
    Prints X-RateLimit-Remaining after each repo. Stops with a warning if < 5.
    If raw_dir is given, each repo's raw response is saved to disk BEFORE it is
    parsed, so a parse crash never loses data that was already fetched."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    raw_responses: list[dict] = []
    signals: list[Signal] = []

    for i, repo in enumerate(WATCHLIST):
        response = requests.get(
            f"{GITHUB_API}/{repo}/releases",
            params={"per_page": 10},
            headers=headers,
            timeout=30,
        )
        remaining = response.headers.get("X-RateLimit-Remaining")
        print(f"{repo}: X-RateLimit-Remaining={remaining}")

        releases = response.json()
        entry = {"repo": repo, "releases": releases}
        raw_responses.append(entry)
        if raw_dir is not None:
            (raw_dir / f"github_{i}.json").write_text(json.dumps(entry), encoding="utf-8")

        signals.extend(parse_release(repo, release) for release in releases)

        if remaining is not None and int(remaining) < 5:
            print(f"WARNING: GitHub rate limit low ({remaining} remaining), stopping")
            break

    return raw_responses, signals
