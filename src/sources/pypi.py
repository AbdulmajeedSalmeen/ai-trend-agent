import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.schema import Signal

PYPI_API = "https://pypi.org/pypi"
PROJECT_URL = "https://pypi.org/project"


def parse_upload_time(files: list[dict]) -> datetime | None:
    """A version is published when its first file lands. Files without a readable
    timestamp are skipped rather than guessed at."""
    times = []

    for item in files:
        stamp = item.get("upload_time_iso_8601") or item.get("upload_time")

        if not stamp:
            continue

        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue

        times.append(parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc))

    return min(times) if times else None


def trim(package: str, payload: dict, since: datetime) -> dict:
    """Keep only what a signal needs. A full PyPI document runs to hundreds of
    kilobytes of file hashes we never read, and the raw cache has to stay small
    enough to live beside the run."""
    recent = {}

    for version, files in (payload.get("releases") or {}).items():
        published = parse_upload_time(files)

        if published is not None and published >= since:
            recent[version] = published.isoformat()

    return {
        "package": package,
        "latest": (payload.get("info") or {}).get("version"),
        "released": recent,
    }


def parse_release(package: str, version: str, published_at: str) -> Signal:
    """tier=1, source='pypi'. The title carries the version so the shared
    extractor reads it the same way it reads a GitHub release title."""
    return Signal(
        id=f"pypi_{package}_{version}",
        source="pypi",
        tier=1,
        subject=package,
        title=f"{package} {version}",
        url=f"{PROJECT_URL}/{package}/{version}/",
        published_at=datetime.fromisoformat(published_at),
    )


def fetch_one(package: str, since: datetime, timeout: int = 30) -> dict:
    """One package. Never raises: a package that 404s or times out comes back as
    an error entry so the rest of the run continues without it."""
    try:
        response = requests.get(
            f"{PYPI_API}/{package}/json",
            headers={"Accept": "application/json", "Accept-Encoding": "gzip"},
            timeout=timeout,
        )

        if response.status_code != 200:
            return {"package": package, "error": f"http {response.status_code}"}

        return trim(package, response.json(), since)
    except (requests.RequestException, ValueError) as problem:
        return {"package": package, "error": type(problem).__name__}


def fetch_pypi(
    packages: list[str], days: int = 30, raw_dir: Path | None = None, workers: int = 6
) -> tuple[list[dict], list[Signal]]:
    """Every release of every tracked package published in the last `days`.

    PyPI is the registry a student's `pip install` actually reads, so it answers
    the question the curriculum comparison asks. There is no token and no rate
    limit to budget for, but there are dozens of packages, so they are fetched in
    a small pool and each failure is isolated."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    raw_responses: list[dict] = []
    signals: list[Signal] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda name: fetch_one(name, since), packages))

    failed = []

    for index, entry in enumerate(results):
        raw_responses.append(entry)

        if raw_dir is not None:
            (raw_dir / f"pypi_{index}.json").write_text(json.dumps(entry), encoding="utf-8")

        if "error" in entry:
            failed.append(f"{entry['package']} ({entry['error']})")
            continue

        for version, published_at in entry["released"].items():
            signals.append(parse_release(entry["package"], version, published_at))

    if failed:
        print(f"pypi: {len(failed)} packages could not be read: {', '.join(failed[:6])}")

    return raw_responses, signals
