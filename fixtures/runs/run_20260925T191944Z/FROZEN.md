# Frozen demo run

Collected 2026-09-25, the day before the demo. This is the run we present from, and the only
one kept in the repo. Every source reads the same 30 days: GitHub releases, PyPI releases and
Hacker News stories. Install counts are complete for all 38 subjects; pypistats refused one
of them during collection, and crewai's was read a few minutes later.

Replay it end to end without touching the network:

    python -m src.pipeline --run-id run_20260925T191944Z

Rebuild the offline page from it:

    python -m web.site --run-id run_20260925T191944Z

`raw/` is the cached HTTP responses from collection. It stays out of the repo; replay does
not need it, because `signals.json`, `market.json` and `packages.json` already hold
everything the later stages read.

Do not overwrite these files. To experiment, start a new run.
