# Team Plan — AI Trend Agent

**Team of 4. Build window: Sep 15 → Sep 26. Demo week starts Sep 27.**

The system: pull AI-ecosystem news (Hacker News + GitHub releases), group it into trends,
**verify claims against official sources**, score each trend, and recommend curriculum updates.
The selling point is verification: our agent says "confirmed, here is the release page" or
"unverified, nobody official said this" — it never presents gossip as fact.

## Architecture

```
 [Stage 1  INGEST]   src/stages/stage1_ingest.py    -> signals.json          (Member B)
 [Stage 2a CLUSTER]  src/stages/stage2a_cluster.py  -> trends.json           (Member C)
 [Stage 2b VERIFY]   src/stages/stage2b_verify.py   -> trends.json updated   (Member D)
 [Stage 3  SCORE]    src/stages/stage3_score.py     -> scores.json           (Member D)
 [Stage 4  ACT]      src/stages/stage4_act.py       -> recommendations.json  (Lead)
 [PIPELINE]          src/pipeline.py  (LangGraph wires all stages)           (Lead)
 [WEBSITE]           built last by Claude (Sep 23-24), reads the JSON files only.
                     No member builds frontend. Team's only job: stable artifacts
                     + one cached real run by Sep 22 evening.
```

Every stage is a file with one entry function:

```python
def run(run_dir: Path) -> None:
    # read the JSON file(s) the previous stage wrote
    # do your work
    # write your JSON file
```

Stages never call each other. They meet only through files in `fixtures/runs/<run_id>/`.
That is why four people can build four stages at the same time.

## The data contract (agreed in the Day-2 workshop — do not change alone)

All files live in `fixtures/runs/<run_id>/`. A run_id looks like `run_20260916T090000Z`.

**signals.json** — list of Signal:
```json
{
  "id": "hn_45123877",
  "source": "hackernews",
  "tier": 2,
  "subject": null,
  "title": "LangGraph 2.0 released with durable execution",
  "url": "https://news.ycombinator.com/item?id=45123877",
  "published_at": "2026-09-14T08:30:00+00:00",
  "body": ""
}
```
- `source`: `"hackernews"` or `"github"`
- `tier`: 1 = official (GitHub release), 2 = discussion (forum post)
- `subject`: package name if known (`"langgraph"`), null if not. GitHub releases always know it; HN posts usually null.
- `published_at`: must be UTC with timezone. Schema rejects naive datetimes.

**trends.json** — list of Trend:
```json
{
  "id": "trend_001",
  "subject": "langgraph",
  "signal_ids": ["hn_45123877", "gh_langgraph_2.0.0"],
  "claims": [
    {
      "text": "langgraph version 2.0.0 was released",
      "subject": "langgraph",
      "version": "2.0.0",
      "verdict": "unverified",
      "evidence_url": null,
      "confidence": 0.2
    }
  ]
}
```
- Stage 2a creates trends with every claim `"unverified"`, evidence null.
- Stage 2b fills in `verdict`, `evidence_url`, `confidence`.
- `verdict`: `"confirmed"` or `"unverified"`. Nothing else in v1.

**scores.json** — list of Score:
```json
{
  "trend_id": "trend_001",
  "chapter_id": "C6",
  "confidence": 0.9,
  "dimensions": {
    "relevance": 4, "impact": 3, "educational_value": 3,
    "difficulty": 2, "market_relevance": 4
  },
  "provenance": {"relevance": "measured", "impact": "default", "...": "..."},
  "priority": 3.35
}
```
- `chapter_id`: matched chapter from `fixtures/curriculum.json`, or null.
- Every dimension is 1–5. `priority` = weighted sum, weights fixed:
  relevance .25, impact .25, educational_value .20, difficulty .10, market_relevance .20
  (weights must assert to sum 1.0 in code).

**recommendations.json** — list of Recommendation:
```json
{
  "trend_id": "trend_001",
  "action": "update_existing_material",
  "chapter_id": "C6",
  "rationale": "langgraph 2.0.0 confirmed via release page; chapter C6 covers LangGraph and was last updated 2026-08-25."
}
```
- `action`: `update_existing_material` | `add_new_lesson` | `watch`.

## Calendar

| Dates | What | Gate |
|---|---|---|
| Sep 15 | Schema workshop, all 4 together, 90 min. Lead runs it | `schema.py` merged, tests green |
| Sep 16–19 | Solo build, each member their own plan file, fixture data only | Each stage runs + tested |
| Sep 20 | **Integration 1** — all together. Chain stages on fixture data | One command, end to end |
| Sep 21–22 | Live: B real APIs, C swaps in Hugging Face embeddings, D calibrates on real data | Real signals flow |
| Sep 23–24 | **Integration 2** — full live run, cache it. Lead + Claude build dashboard | Run has confirmed AND unverified |
| Sep 25 | Rehearsal 1, timed | Fix list only from what broke |
| Sep 26 | Rehearsal 2, freeze. Offline-fallback drill | Demo ready |

Descope order if late (cut top first, never cut lower ones):
1. LangGraph wrapper (plain function calls fine)
2. Hugging Face embeddings (TF-IDF fine)
3. Never cut: schema tests, verification gate, the confirmed-vs-unverified demo contrast, cached demo run.

## Git — the daily loop (everyone, every day)

```bash
git checkout dev && git pull        # morning, before any work
# ... work, small commits ...
python -m pytest                    # MUST pass before push
git add -A && git commit -m "What changed"
git pull && git push                # pull again first — teammate may have pushed
```

Rules:
1. `pytest` green before every push. Broken dev blocks all four people.
2. Pull before starting, pull before pushing.
3. Never `git push --force`.
4. Changing `src/schema.py`, `fixtures/curriculum.json`, or `requirements.txt` — tell the group BEFORE, in the group chat.

## Daily standup — 15 minutes, same time, no laptops

Each person answers three questions, one minute each:
1. What did I finish yesterday?
2. What will I finish today?
3. What is blocking me?

Lead writes the answers into `docs/PROGRESS.md` the same day.

## When you are stuck

- 30 minutes stuck → ask your buddy (Lead↔C, B↔D).
- 60 minutes stuck → post in group chat, Lead brings it to Claude supervision session.
- Never stay stuck past lunch. Being stuck is normal; hiding it is the only failure.
