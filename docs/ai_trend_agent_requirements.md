# AI Trend Agent — Full Requirements & Build Plan

**Goal:** Turn raw technology signals into a prioritized, evidence-backed curriculum recommendation. Win against 50+ competitors by demonstrating genuine agentic *judgment* (verification + trade-off scoring), not just a content pipeline.

---

## 1. What "Perfect" Looks Like Here

The project brief asks for four things — hit all four, cleanly, with visible reasoning at each step:

1. **Monitor** multiple public sources for new tech/tools/research/industry news.
2. **Group, dedupe, and verify** important claims against reliable/primary sources — preserving evidence and uncertainty.
3. **Compare** each trend against a sample curriculum on relevance, maturity, educational value, prerequisites, and content-development difficulty.
4. **Recommend** an action (watch / update existing material / add optional content / add new lesson / investigate larger change) with an initial action plan.

The single biggest differentiator available to you: **most competitors will skip real verification and just summarize + score with one LLM call.** The brief explicitly rewards "evidence-backed" — build a visible evidence trail (source → claim → verification verdict → confidence) that judges can inspect. That's the moat.

---

## 2. Scope Boundaries (keep it tight)

- **Domain:** pick ONE narrow, information-rich domain — not "AI" broadly. Recommendation: **"Agentic AI tooling & frameworks"** (fitting, self-referential, and you already have grounded knowledge of it from this conversation — LangGraph, CrewAI, Claude Agent SDK, MCP, etc. give you a real evaluation baseline).
- **Curriculum:** a small mock curriculum (8–12 lessons/modules) for a plausible course — e.g. "Applied AI/Data Science Bootcamp Curriculum v1" — as a structured JSON/YAML file, not a live system.
- **Sources:** 3–4 max, not 10. Depth of verification beats breadth of ingestion.
- **Time horizon:** monitor "last 7–14 days" of signals for the demo, not real-time streaming — a scheduled batch run is enough and far more reliable live.
- **Stop at recommendation + action plan.** Do not build the content itself (that's Project 5's job) — a common overreach mistake to explicitly avoid.

---

## 3. Pipeline Architecture (4 stages, explicit and inspectable)

```
[Stage 1: MONITOR]  →  [Stage 2: VERIFY]  →  [Stage 3: SCORE]  →  [Stage 4: RECOMMEND]
   ingest signals        dedupe + fact-check     compare vs curriculum   action + plan
```

### Stage 1 — Monitor / Ingest
- Pull raw signals from each source into a common schema (see §6).
- Sources should be a mix of primary (official release notes, arXiv, GitHub) and secondary (HN, Product Hunt) so Stage 2 has something to cross-check against.
- Output: a list of raw `Signal` objects, timestamped, source-tagged.

### Stage 2 — Group, Dedupe, Verify
This is the stage that wins you the bootcamp. Structure it as its own mini sub-pipeline (based on standard fact-checking agent design: claim detection → evidence retrieval → verification → confidence scoring):
1. **Cluster** raw signals into candidate "trends" (same underlying topic mentioned across sources) via embedding similarity or LLM clustering.
2. **Claim extraction** — pull the 1–3 concrete, checkable claims out of each trend cluster (e.g. "LangGraph reached 1.0 GA in October 2025", not the whole paragraph).
3. **Cross-source verification** — check each claim against at least one *primary* source (official docs/blog, arXiv abstract, GitHub release). If only secondary sources exist, flag as **unverified** rather than dropping it — the brief explicitly wants uncertainty *preserved*, not hidden.
4. **Confidence/credibility score** per claim: source-tier weighting (official docs/paper > reputable outlet > aggregator > forum) + corroboration count.
5. Output: `VerifiedTrend` objects with an attached **evidence list** (source, quote-free paraphrase, tier, verdict: confirmed/partially-confirmed/unverified).

### Stage 3 — Score Against Curriculum
For each `VerifiedTrend`, score against the mock curriculum on the five brief-mandated dimensions:

| Dimension | What it measures | Suggested scale |
|---|---|---|
| Market relevance | How much industry signal/demand exists | 1–5 |
| Maturity | Is this stable enough to teach, or still shifting weekly | 1–5 |
| Educational value | Does understanding it build transferable skill | 1–5 |
| Prerequisite fit | Do learners already have the background, or is there a gap | 1–5 |
| Content-development difficulty | Effort/cost to build teaching material for it | 1–5 (inverse-weighted) |

Combine into a single **priority score** with transparent, tunable weights (e.g. relevance 0.3, maturity 0.2, educational value 0.25, prerequisite fit 0.15, difficulty 0.1 — inverse). Show the weights and the math in the demo; a black-box single number is a missed opportunity to prove "judgment."

### Stage 4 — Recommend + Action Plan
Map score bands + verification confidence to one of the five brief-specified actions:
- **Watch** — low confidence and/or low maturity, revisit later
- **Update existing material** — trend extends/corrects something already in curriculum
- **Add optional content** — solid but niche/elective value
- **Add new lesson** — high priority score + high confidence
- **Investigate larger curriculum change** — high priority score across multiple trends pointing the same direction (e.g. three signals all pointing at "agent orchestration is now core," not peripheral)

Each recommendation ships with: the action, a 2–3 step initial action plan, the evidence trail, and the confidence level — explicitly, in the UI, not just in a log.

---

## 4. Data Sources (concrete, free, no-auth-hassle options)

| Source | Type | Access | Use |
|---|---|---|---|
| Hacker News (Algolia API) | Secondary/community signal | Free, no key, `hn.algolia.com/api/v1/search` | velocity/sentiment signal, initial detection |
| GitHub Trending / Releases API | Primary (for tool releases) | Free, GitHub REST API | verification of "X shipped version Y" claims |
| arXiv API | Primary (research) | Free, no key | verification of research-based trend claims |
| Official project blogs/changelogs (LangGraph, CrewAI, Anthropic, OpenAI, Google ADK release notes) | Primary | web_fetch / RSS | top-tier verification source |
| Product Hunt | Secondary | Free tier API | optional, tooling/product angle |

Rationale: this mix gives Stage 2 real primary-vs-secondary contrast to work with — HN mentions something → agent checks if there's a primary-source release note or paper confirming it → confidence score reflects whether it found one.

---

## 5. Agent Architecture / Framework Choice

Current (2026) framework landscape assessment:
- **LangGraph** is the production standard for stateful, auditable, multi-stage workflows with explicit branching and checkpointing — exactly what a monitor→verify→score→recommend pipeline needs, and it produces the kind of visible state/audit trail that supports your differentiation strategy.
- **CrewAI** is faster to prototype (role-based crews) but has less explicit control over conditional routing and is weaker on the "show your reasoning trail" requirement.
- **Claude Agent SDK** is a strong alternative if you want native Anthropic tool-use and subagent spawning without adopting a separate orchestration framework.

**Recommendation:** Use **LangGraph** (or a lightweight hand-rolled state graph if time is short) with 4 explicit nodes matching the 4 pipeline stages, each with its own system prompt and tool access. This maps directly onto the brief's stages, gives you checkpointing (rerun Stage 3 without re-verifying Stage 2), and produces a natural audit log to show judges.

If time is very tight: a hand-rolled sequential Python pipeline (functions, not a framework) with structured JSON outputs at each stage is a legitimate fallback — judges care about the *reasoning quality shown*, not the framework name.

---

## 6. Data Schema (design this first — everything else follows)

```json
// Signal (Stage 1 output)
{
  "id": "sig_001",
  "source": "hackernews",
  "source_tier": "secondary",
  "title": "...",
  "url": "...",
  "published_at": "2026-08-10",
  "raw_snippet": "..."
}

// VerifiedTrend (Stage 2 output)
{
  "trend_id": "trend_014",
  "label": "LangGraph durable execution features",
  "signals": ["sig_001", "sig_004", "sig_009"],
  "claims": [
    {
      "claim": "LangGraph added per-node timeouts and durable streaming in Q2 2026",
      "verdict": "confirmed",
      "confidence": 0.9,
      "evidence": [
        {"source": "LangGraph official release notes", "tier": "primary", "url": "..."},
        {"source": "Hacker News discussion", "tier": "secondary", "url": "..."}
      ]
    }
  ],
  "overall_confidence": 0.85
}

// CurriculumMatch (Stage 3 output)
{
  "trend_id": "trend_014",
  "scores": {
    "market_relevance": 4,
    "maturity": 4,
    "educational_value": 5,
    "prerequisite_fit": 3,
    "dev_difficulty": 2
  },
  "priority_score": 3.75,
  "matched_curriculum_module": "Module 6: Agent Orchestration"
}

// Recommendation (Stage 4 output)
{
  "trend_id": "trend_014",
  "action": "update_existing_material",
  "action_plan": [
    "Add a durable-execution section to Module 6 lecture notes",
    "Update the LangGraph lab to demonstrate checkpointing",
    "Flag for instructor review before next cohort"
  ],
  "confidence": 0.85,
  "evidence_summary": "2 primary + 1 secondary source, confirmed"
}
```

---

## 7. Mock Curriculum (build this as a fixture, not live)

A JSON/YAML file with ~8–12 modules, each with: `module_id`, `title`, `topics_covered`, `prerequisites`, `last_updated`. This is what Stage 3 compares trends against. Keep it plausible and consistent with your chosen domain (e.g. a "Practical AI/Agentic Systems" bootcamp curriculum) so the recommendations look grounded rather than arbitrary.

---

## 8. Interface / Demo Format

Recommendation: **Streamlit dashboard** with three views —
1. **Trend Radar** — table/scatter of all detected trends by priority score and confidence (this is your "wow" visual — a 2D plot of confidence vs. priority score, color-coded by recommended action, is a strong visual centerpiece).
2. **Trend Detail** — click into any trend → see the full evidence trail (sources, verdicts, scoring breakdown, recommendation, action plan). This is where you prove the "evidence-backed" claim to judges live.
3. **Run Log** — the agent's stage-by-stage reasoning trace (what it searched, what it found, what it discarded and why) — proves genuine agentic behavior rather than a canned demo.

---

## 9. AIDC Integration Requirement

Build the pipeline against a standard model API (Anthropic API) first. Leave one clearly swappable call point — ideally the Stage 2 verification call or the Stage 4 recommendation call — behind a thin adapter function so that pointing it at an AIDC-provided endpoint for the final demo is a one-line config change, not a rewrite.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Recommendation looks arbitrary if curriculum is thin | Build a genuinely plausible 8–12 module curriculum with real prerequisite structure |
| Verification stage silently hallucinates a "confirmed" verdict | Force the agent to cite a specific source per claim; if it can't produce one, verdict must default to "unverified" — never let the LLM self-certify without a retrieved source |
| Domain too broad → noisy trends | Narrow to "agentic AI tooling" specifically, not "AI" generally |
| Live demo API/network flakiness | Cache a known-good run's data as fallback; demo from cache if live pull fails, mention it's cached |
| Scope creep into content generation | Hard stop at Stage 4 output — do not build a 5th "generate the lesson" stage |

---

## 11. Build Order (suggested milestones)

1. Define schema (§6) + mock curriculum (§7) — do this first, everything depends on it.
2. Build Stage 1 ingestion for 2 sources (HN + one primary source) — get real data flowing.
3. Build Stage 2 verification with a hard-coded test trend before wiring it to live Stage 1 output — validate the evidence-trail logic in isolation.
4. Build Stage 3 scoring against the mock curriculum.
5. Build Stage 4 recommendation mapping.
6. Wire all 4 stages into LangGraph (or sequential pipeline) end-to-end.
7. Build the Streamlit dashboard (Trend Radar → Detail → Run Log).
8. Swap in AIDC endpoint for one call.
9. Rehearse the demo narrative: raw noisy signals → verified trend → scored → recommended, with the evidence trail visible at every click.

---

## 12. Demo Narrative (what you say while clicking)

"Here are 40 raw signals from the last two weeks. Watch the agent cluster them into 12 candidate trends, then verify each claim against a primary source — this one gets confirmed because we found the official release notes, this one stays flagged unverified because we could only find a forum post. Now it scores each verified trend against our curriculum on five dimensions — here's the math, not a black box. And here's the final call: update Module 6, with a concrete 3-step plan, backed by the evidence you just watched it check."

That's the full loop the brief asks for, shown transparently — which is the difference between "a agent that generates a report" and "an agent that reasons its way to a decision."
