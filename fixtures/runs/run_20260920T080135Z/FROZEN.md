# Frozen demo run

Collected 2026-09-20. This is the run we present from, and the only one kept in the repo.

Replay it end to end without touching the network:

    python -m src.pipeline --run-id run_20260920T080135Z

Rebuild the offline page from it:

    python -m web.site --run-id run_20260920T080135Z

`raw/` is the cached HTTP responses from collection. It stays out of the repo; replay does
not need it, because `signals.json` already holds everything the later stages read.

Do not overwrite these files. To experiment, start a new run.
