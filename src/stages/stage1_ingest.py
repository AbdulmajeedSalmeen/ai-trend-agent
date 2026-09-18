import os
from pathlib import Path

from dotenv import load_dotenv

from src import runio
from src.sources import github_releases, hackernews

HN_QUERIES = ["langgraph", "langchain", "openai", "claude", "hugging face", "ai agent"]


def run(run_dir: Path) -> None:
    load_dotenv()
    token = os.environ.get("GITHUB_TOKEN")
    raw_dir = run_dir / "raw"

    _hn_raw, hn_signals = hackernews.fetch_hackernews(HN_QUERIES, raw_dir=raw_dir)
    _gh_raw, gh_signals = github_releases.fetch_github_releases(token, raw_dir=raw_dir)

    seen_urls: set[str] = set()
    signals = []
    for signal in hn_signals + gh_signals:
        if signal.url in seen_urls:
            continue
        seen_urls.add(signal.url)
        signals.append(signal)

    print(
        f"hackernews: {len(hn_signals)} signals, "
        f"github: {len(gh_signals)} signals, "
        f"after dedupe: {len(signals)}"
    )

    runio.save_artifact(run_dir, "signals", signals)
