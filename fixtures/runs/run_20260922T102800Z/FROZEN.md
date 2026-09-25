# Frozen demo run

Collected 2026-09-22. This is the run we present from, and the only one kept in the repo.
Every source reads the same 30 days: GitHub releases, PyPI releases and Hacker News stories.

pypistats refused during collection. Install counts were filled afterwards, one request at
a time, until all 37 subjects had one, the last of them on Sep 25. Scores and recommendations
were then replayed from these files, with no network and no change to any decision.

Replay it end to end without touching the network:

    python -m src.pipeline --run-id run_20260922T102800Z

Rebuild the offline page from it:

    python -m web.site --run-id run_20260922T102800Z

`raw/` is the cached HTTP responses from collection. It stays out of the repo; replay does
not need it, because `signals.json` and `market.json` already hold everything the later
stages read.

Do not overwrite these files. To experiment, start a new run.
