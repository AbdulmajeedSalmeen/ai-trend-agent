import os
from pathlib import Path

from dotenv import load_dotenv

from src import runio
from src.schema import MarketSignal, PackageFacts, Signal
from src.curriculum import tracked_packages
from src.sources import github_releases, hackernews, market, pypi

HN_QUERIES = ["langgraph", "langchain", "openai", "claude", "hugging face", "ai agent"]

# Every source reads the same stretch of time, so a busy project and a quiet one
# are compared over the same days.
WINDOW_DAYS = 30


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

    _hn_raw, hn_signals = hackernews.fetch_hackernews(HN_QUERIES, raw_dir=raw_dir, days=WINDOW_DAYS)
    _gh_raw, gh_signals = github_releases.fetch_github_releases(token, raw_dir=raw_dir, days=WINDOW_DAYS)

    packages = tracked_packages()
    print(f"pypi: following {len(packages)} packages the course installs")
    _pypi_raw, pypi_signals = pypi.fetch_pypi(packages, days=WINDOW_DAYS, raw_dir=raw_dir)

    signals = dedupe_by_url(gh_signals + pypi_signals + hn_signals)

    print(
        f"hackernews: {len(hn_signals)} signals, "
        f"github: {len(gh_signals)} signals, "
        f"pypi: {len(pypi_signals)} signals, "
        f"after dedupe: {len(signals)}"
    )

    runio.save_artifact(run_dir, "signals", signals)

    subjects = sorted({signal.subject for signal in signals if signal.subject})
    demand = market.fetch_market(subjects, raw_dir=raw_dir)
    runio.save_artifact(run_dir, "market", [
        MarketSignal(subject=subject, **{key: value for key, value in entry.items()})
        for subject, entry in demand.items()
    ])

    runio.save_artifact(run_dir, "packages", package_facts(subjects))


def package_facts(subjects: list[str]) -> list[PackageFacts]:
    """Each subject's whole history on PyPI, which maturity and prerequisites are
    judged from. A subject PyPI has no record of is left out and scores default."""
    names = {subject: market.pypi_name(subject) for subject in subjects}
    facts = pypi.fetch_facts(sorted(set(names.values())))
    found = [PackageFacts(subject=subject, **facts[name]) for subject, name in names.items() if facts.get(name)]
    print(f"pypi: history for {len(found)} of {len(subjects)} subjects")
    return found
