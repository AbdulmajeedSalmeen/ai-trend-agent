# Member B — Stage 1: Ingestion

**Mission:** everything downstream is only as good as what you pull in. You fetch AI news
from two real APIs, normalize it into `Signal` objects, cache every raw response, and
write `signals.json`. When your stage works, the team has real-world data; until then,
everyone codes against hand-made samples.

**You will learn:** calling REST APIs with `requests`, pagination, rate limits, API tokens,
UTC time handling, caching, defensive logging.

**Files you own:**
- `src/sources/hackernews.py`
- `src/sources/github_releases.py`
- `src/stages/stage1_ingest.py`
- `tests/test_stage1.py`

**Your contract:** read nothing. Write `signals.json` (list of `Signal`, see TEAM-PLAN.md).
Also save every raw API response into `<run_dir>/raw/` before parsing it.

---

## Sep 16 — explore the APIs by hand, save real samples

Do NOT write module code today. First understand what the APIs return.

Open a Python shell (`python` in the repo folder, venv active) and run:

```python
import requests, json
r = requests.get(
    "https://hn.algolia.com/api/v1/search_by_date",
    params={"query": "langgraph", "tags": "story", "hitsPerPage": 20},
    timeout=30,
)
data = r.json()
print(len(data["hits"]))
print(json.dumps(data["hits"][0], indent=2))
```

Read one hit carefully. Notice:
- `created_at_i` = unix timestamp (seconds). This becomes `published_at`.
- `objectID` = unique id. Signal id = `"hn_" + objectID`.
- some hits have `"url": null` — the story has no outside link. Use the HN permalink
  instead: `https://news.ycombinator.com/item?id=<objectID>`. About 9 of every 100 hits.

Save one full response as your test fixture:

```python
from pathlib import Path
Path("fixtures/samples").mkdir(exist_ok=True)
Path("fixtures/samples/hn_sample.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
```

Same exercise for GitHub releases:

```python
r = requests.get(
    "https://api.github.com/repos/langchain-ai/langgraph/releases",
    params={"per_page": 10},
    timeout=30,
)
print(r.status_code, r.headers.get("X-RateLimit-Remaining"))
releases = r.json()
print(json.dumps(releases[0], indent=2)[:2000])
```

Notice: `tag_name` (version), `published_at` (ISO string, already UTC), `html_url`, `body`
(the changelog text). Save as `fixtures/samples/github_sample.json`.

**Rate limit warning:** without a token GitHub allows 60 requests/hour and you just spent
some. Create a token now: github.com → Settings → Developer settings →
Personal access tokens → Fine-grained → generate, no special permissions needed,
copy it. Then create a file `.env` in the repo root (it is gitignored — NEVER commit it):

```
GITHUB_TOKEN=github_pat_XXXXXXXX
```

With the token: 5,000 requests/hour.

Commit today: the two sample files + a note in PROGRESS.md what you learned.

## Sep 17 — parse functions + tests (no network in tests!)

`src/sources/hackernews.py`:

```python
from datetime import datetime, timezone

from src.schema import Signal


def parse_hn_hit(hit: dict) -> Signal:
    """One Algolia hit -> one Signal. tier=2, source='hackernews', subject=None."""
    # TODO:
    #  id        = "hn_" + hit["objectID"]
    #  url       = hit["url"] or the permalink (see Sep 16 notes)
    #  published_at = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
    #  title     = hit["title"]
    ...


def fetch_hackernews(queries: list[str], max_pages: int = 3) -> tuple[list[dict], list[Signal]]:
    """Returns (raw_responses, signals). Loops queries, pages through results.
    MUST print a line 'TRUNCATED query=<q>' when nbPages > max_pages,
    so we can see when we are sampling instead of reading everything."""
    ...
```

`src/sources/github_releases.py`:

```python
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
    """tier=1, source='github', subject = repo name after the slash, lowercased.
    id = 'gh_<subject>_<tag_name>'. published_at: datetime.fromisoformat works on
    GitHub's format after replacing the trailing 'Z' with '+00:00'."""
    ...


def fetch_github_releases(token: str | None) -> tuple[list[dict], list[Signal]]:
    """Header: {'Authorization': f'Bearer {token}'} if token else {}.
    Print 'X-RateLimit-Remaining' after each repo. Stop and print a warning if < 5."""
    ...
```

Tests — they load your SAVED SAMPLES, never the network:

```python
import json
from pathlib import Path

from src.sources.hackernews import parse_hn_hit


def load_sample(name):
    return json.loads(Path(f"fixtures/samples/{name}").read_text(encoding="utf-8"))


def test_hn_hit_becomes_signal():
    hit = load_sample("hn_sample.json")["hits"][0]
    s = parse_hn_hit(hit)
    assert s.source == "hackernews"
    assert s.tier == 2
    assert s.published_at.tzinfo is not None   # UTC enforced


def test_hn_hit_without_url_gets_permalink():
    hit = load_sample("hn_sample.json")["hits"][0]
    hit["url"] = None
    s = parse_hn_hit(hit)
    assert "news.ycombinator.com" in s.url
```

Plus the same pair for GitHub. Run `python -m pytest tests/test_stage1.py -v` until green.

## Sep 18 — the stage itself

`src/stages/stage1_ingest.py`:

```python
import json
import os
from pathlib import Path

from src import runio
from src.sources import github_releases, hackernews

HN_QUERIES = ["langgraph", "langchain", "openai", "claude", "hugging face", "ai agent"]


def run(run_dir: Path) -> None:
    # 1. load .env:  from dotenv import load_dotenv; load_dotenv()
    # 2. fetch both sources
    # 3. save every raw response: (run_dir / "raw" / "hn_0.json").write_text(...)
    #    RAW FIRST, parse second — if parsing crashes, the data is already safe on disk
    # 4. deduplicate signals by url (two HN queries often return the same story)
    # 5. print counts:  "hackernews: 143 signals, github: 61 signals, after dedupe: 187"
    # 6. runio.save_artifact(run_dir, "signals", signals)
    ...
```

Test with a real run:

```bash
python -c "from pathlib import Path; from src import runio; from src.stages import stage1_ingest; rd = runio.run_dir(runio.new_run_id()); stage1_ingest.run(rd); print(rd)"
```

Open the printed folder — check `signals.json` by eye: real titles, timestamps end with
`+00:00`, both sources present.

## Sep 19 — hardening + PR

- Dedupe test: two fake signals, same url → one survives.
- Timeout on every `requests.get` (`timeout=30`) — a hung request must not hang the pipeline.
- What happens when GitHub returns 403 (rate limited)? Catch it, print a clear line,
  return the signals you already have. Partial data beats a crash.
- `pytest` fully green, push, tell Lead stage 1 is done.

## Traps (each one cost the original build hours)

1. **60 requests/hour without a token.** Get the token Sep 16, first thing.
2. **Raw responses saved BEFORE parsing.** Crash after saving = data safe. Crash before = fetch again, burn rate limit again.
3. **Naive datetimes.** `datetime.fromtimestamp(x)` without `tz=` gives local time — schema rejects it. Always `tz=timezone.utc`.
4. **Truncation is silent.** If a query has 400 results and you read 60, nothing errors — you just sampled 15% and didn't know. Print `TRUNCATED` loudly.
5. **Tests never touch the network.** Saved samples only. Network tests fail in CI and burn rate limits.

## Definition of done

- [ ] Both parse functions + fetch functions written
- [ ] 6+ tests green, all offline
- [ ] One real run produced `signals.json` with 100+ signals, both sources
- [ ] Raw responses cached in `raw/`
- [ ] Counts + TRUNCATED logging prints
- [ ] Pushed to dev, Lead informed
