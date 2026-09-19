# AI Trend Agent — Team Build

Detects AI ecosystem trends, verifies claims against primary sources, recommends curriculum updates.

## Team

- (add yourself by PR)

## Setup

    python -m venv .venv
    source .venv/Scripts/activate
    pip install -r requirements.txt
    pytest

## Running it

The pipeline writes JSON artifacts into `fixtures/runs/<run_id>/`. Nothing else reads
the network, so every later step works offline.

### The web app (collect, re-analyse and read a run from the browser)

    python -m uvicorn web.server:app --port 8800

Open http://localhost:8800 — pick a saved run, press **Run now** to collect this week
live, or **Re-analyse** to replay the saved signals of the selected run without touching
the network. Progress and per-stage logs appear while it runs.

### One command, no browser

    python -m src.pipeline                      # live: collect and analyse
    python -m src.pipeline --run-id run_2026...  # replay saved signals, no network

### The offline page (what we present from)

    python -m web.site --run-id run_2026...

Writes `web/dist/site.html` with the run and its fonts embedded. Open the file on any
machine: no server, no network.
