# AI Trend Agent - Team Build

Reads what shipped in the AI ecosystem this week, checks every claim against the official
release that would have to confirm it, then compares the confirmed versions with what the
bootcamp's own notebooks install. The output is a recommendation with its reason attached.

## Team

| Member | Owns |
|---|---|
| Abdulmajeed Salmeen | Schema, run I/O, Stage 4, pipeline, web server, dashboard, repo |
| Ali Almufarriji | Stage 1 - collecting signals from Hacker News and GitHub |
| Abdulrhman Almania | Stage 2a - clustering signals into subjects and extracting claims |
| Naif Alasmari | Stage 2b verification, and Stage 3 scoring |

## Setup

    python -m venv .venv
    source .venv/Scripts/activate
    pip install -r requirements.txt
    pytest

PowerShell uses `;` between commands and `.\.venv\Scripts\python.exe`; Git Bash uses `&&`
and `.venv/Scripts/python.exe`.

A model reads discussion posts, judges how much a change matters for teaching, and writes
the recommendation sentence. Put a key in `.env` to switch it on:

    OPENAI_API_KEY=sk-...

Without it the stages fall back to rules and say so on the page. **No test ever calls a
model or the network.**

## Running it

The pipeline writes JSON artifacts into `fixtures/runs/<run_id>/`. Only Stage 1 touches the
network, so every later step works offline.

### The web app (collect, re-analyse and read a run from the browser)

    python -m uvicorn web.server:app --port 8800

Open http://localhost:8800 - pick a saved run, press **Run now** to collect this week
live, or **Re-analyse** to replay the saved signals of the selected run without touching
the network. The stages report what they are thinking while they work.

### One command, no browser

    python -m src.pipeline                       # live: collect and analyse
    python -m src.pipeline --run-id run_2026...  # replay saved signals, no network

### The offline page (what we present from)

    python -m web.site --run-id run_2026...

Writes `web/dist/site.html` with the run and its fonts embedded. Open the file on any
machine: no server, no network.

## Reading the course into the agent

The agent cannot say a chapter is behind unless it knows what that chapter runs. That comes
from the course notebooks themselves.

    python -m src.curriculum

Put each week's material in `notebooks/week <n>/` first. The scan records, per chapter, the
version each notebook installs, the packages it installs with no version bound at all, and
the API calls a later major release removed. `notebooks/` is gitignored: the course files
stay on your machine.

    python -m src.notebooks --by-week    # what the scan sees, before it is written
    python -m src.pin                    # what each chapter is recorded as running

## Layout

    src/       the agent: schema, run I/O, the five stages, the model adapter
    web/       the website: builder, FastAPI server, template, styles
    fixtures/  curriculum.json and the saved runs
    docs/      progress, tuning notes, demo answers, the per-member plans
