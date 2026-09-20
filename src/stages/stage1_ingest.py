import os
from pathlib import Path

from dotenv import load_dotenv

from src import runio
from src.schema import Signal
from src.curriculum import tracked_packages
from src.sources import github_releases, hackernews, pypi

HN_QUERIES = ["langgraph", "langchain", "openai", "claude", "hugging face", "ai agent"]


def dedupe_by_url(signals: list[Signal]) -> list[Signal]:
    """Two HN queries (or an HN post and its own GitHub release) can point at the
    same url. Keep the first signal seen for each url, drop the rest."""
    seen_urls: set[str] = set()
    deduped = []
    for signal in signals:
        if signal.url in seen_urls:
            continue
        seen_urls.add(signal.url)
        deduped.append(signal)
    return deduped


def run(run_dir: Path) -> None:
    load_dotenv()
    token = os.environ.get("GITHUB_TOKEN")
    raw_dir = run_dir / "raw"

    _hn_raw, hn_signals = hackernews.fetch_hackernews(HN_QUERIES, raw_dir=raw_dir)
    _gh_raw, gh_signals = github_releases.fetch_github_releases(token, raw_dir=raw_dir)

    packages = tracked_packages()
    print(f"pypi: following {len(packages)} packages the course installs")
    _pypi_raw, pypi_signals = pypi.fetch_pypi(packages, raw_dir=raw_dir)

    signals = dedupe_by_url(gh_signals + pypi_signals + hn_signals)

    print(
        f"hackernews: {len(hn_signals)} signals, "
        f"github: {len(gh_signals)} signals, "
        f"pypi: {len(pypi_signals)} signals, "
        f"after dedupe: {len(signals)}"
    )

    runio.save_artifact(run_dir, "signals", signals)
