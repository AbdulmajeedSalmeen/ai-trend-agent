import argparse
import json
from pathlib import Path

from src import concepts, memory, runio
from src.schema import Recommendation, Score, Signal, Trend

CURRICULUM_PATH = Path("fixtures/curriculum.json")
TEMPLATE_PATH = Path("web/template.html")
FONTS_PATH = Path("web/fonts.css")
STYLE_PATH = Path("web/style.css")


def read_run(run_dir: Path) -> dict:
    artifacts = {}
    for name, model in [
        ("signals", Signal),
        ("trends", Trend),
        ("scores", Score),
        ("recommendations", Recommendation),
    ]:
        path = run_dir / f"{name}.json"
        artifacts[name] = runio.load_artifact(run_dir, name, model) if path.exists() else []
    return artifacts


def read_trace(run_dir: Path) -> dict | None:
    path = run_dir / "trace.json"

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8")).get("summary")


def build_payload(run_dir: Path) -> dict:
    artifacts = read_run(run_dir)
    curriculum = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))

    signals = {s.id: s for s in artifacts["signals"]}
    scores = {s.trend_id: s for s in artifacts["scores"]}
    trends = {t.id: t for t in artifacts["trends"]}

    sources = {}
    for signal in artifacts["signals"]:
        sources[signal.source] = sources.get(signal.source, 0) + 1

    # A run collects a month of releases every time, so two runs a day apart look
    # almost identical. What separates them is what arrived since the last one.
    previous = memory.previous_run(run_dir.name)
    since = memory.run_started(previous) if previous else None
    fresh = sum(1 for s in artifacts["signals"] if since and s.published_at > since)
    started = memory.run_started(run_dir.name)

    items = []
    for rec in artifacts["recommendations"]:
        trend = trends.get(rec.trend_id)
        score = scores.get(rec.trend_id)
        if trend is None or score is None:
            continue

        claims = []
        for claim in trend.claims:
            origin = signals.get(claim.source_signal_id or "")
            claims.append(
                {
                    "text": claim.text,
                    "version": claim.version,
                    "verdict": claim.verdict,
                    "kind": claim.evidence_kind,
                    "evidence_url": claim.evidence_url,
                    "origin_source": origin.source if origin else None,
                    "origin_url": origin.url if origin else None,
                    "origin_title": origin.title if origin else None,
                }
            )

        confirmed = sum(1 for c in claims if c["verdict"] == "confirmed")
        # When an ask began, not only how many runs it has lasted. Nine runs reads
        # like nine weeks, and on a day of testing it can be one afternoon.
        first = memory.run_started(rec.first_seen_run or "") if rec.runs_flagged > 1 else None
        items.append(
            {
                "trend_id": trend.id,
                "subject": trend.subject,
                "family": trend.subject.replace("_", "-").split("-")[0],
                "action": rec.action,
                "chapter_id": rec.chapter_id,
                "rationale": rec.rationale,
                "rationale_by": rec.rationale_by,
                "rationale_ar": rec.rationale_ar,
                "action_plan": rec.action_plan,
                "action_plan_ar": rec.action_plan_ar,
                "edits": rec.edits,
                "chapter_version": rec.chapter_version,
                "latest_version": rec.latest_version,
                "gap_kind": rec.gap_kind,
                "releases_since": rec.releases_since,
                "legacy_uses": rec.legacy_uses,
                "runs_flagged": rec.runs_flagged,
                "first_seen_run": rec.first_seen_run,
                "asked_since": first.date().isoformat() if first else None,
                "asked_days": (started - first).days if first and started else None,
                "version_moved": rec.version_moved,
                "priority": round(score.priority, 2),
                "confidence": round(score.confidence, 2),
                "dimensions": score.dimensions,
                "provenance": score.provenance,
                "changes": {k: score.changes.get(k, 0) for k in ("breaking", "deprecation", "feature", "fix", "noise")}
                           | {"highlights": score.changes.get("highlights", [])[:3]} if score.changes else {},
                "market": score.market,
                "signal_count": len(trend.signal_ids),
                "confirmed": confirmed,
                "unverified": len(claims) - confirmed,
                "claims": claims,
            }
        )

    items.sort(key=lambda i: (-i["priority"], i["subject"]))

    all_claims = [c for i in items for c in i["claims"]]
    kinds = {"cross_source": 0, "registry_match": 0, "primary_report": 0, "unverified": 0}
    for claim in all_claims:
        kinds[claim["kind"] or "unverified"] += 1

    chapters = []
    for chapter in curriculum["chapters"]:
        chapters.append(
            {
                "chapter_id": chapter["chapter_id"],
                "title": chapter["title"],
                "week": chapter.get("week"),
                "topics": chapter.get("topics_covered", []),
                "tools": chapter.get("tools_covered", []),
                "teaches": chapter.get("teaches", ""),
                "teaches_ar": chapter.get("teaches_ar"),
                "pins": chapter.get("pins", {}),
                "unpinned": chapter.get("installs_unpinned", []),
                "legacy_api": chapter.get("legacy_api", []),
                "notebooks": len(chapter.get("notebooks", [])),
                "last_updated": chapter.get("last_updated"),
                "edits": len(chapter.get("material_edits", [])),
                "edits_breaking": sum(1 for edit in chapter.get("material_edits", [])
                                      if edit["runs_as_pinned"] is False),
            }
        )

    return {
        "run_id": run_dir.name,
        "curriculum_name": curriculum.get("name", ""),
        "curriculum_sources": curriculum.get("sources", []),
        "counts": {
            "signals": len(artifacts["signals"]),
            "sources": sources,
            "trends": len(artifacts["trends"]),
            "claims": len(all_claims),
            "recommendations": len(items),
            "update": sum(1 for i in items if i["action"] == "update_existing_material"),
            "new_lesson": sum(1 for i in items if i["action"] == "add_new_lesson"),
            "optional": sum(1 for i in items if i["action"] == "add_optional_content"),
            "investigate": sum(1 for i in items if i["action"] == "investigate_larger_change"),
            "edits": sum(len(i["edits"]) for i in items),
            "edits_breaking": sum(1 for i in items for edit in i["edits"] if edit["runs_as_pinned"] is False),
            "not_taught": sum(1 for i in items if not i["chapter_id"]),
            "watch": sum(1 for i in items if i["action"] == "watch"),
            "kinds": kinds,
            "chapters": len(chapters),
            "chapters_touched": len({i["chapter_id"] for i in items if i["chapter_id"]}),
            "fresh_signals": fresh,
            "new_asks": sum(1 for i in items if i["action"] != "watch" and i["runs_flagged"] == 1),
            "standing_asks": sum(1 for i in items if i["action"] != "watch" and i["runs_flagged"] > 1),
        },
        "previous_run": previous,
        "material_checked": curriculum.get("material_checked"),
        "concepts_checked": curriculum.get("concepts_checked"),
        "trace": read_trace(run_dir),
        "items": items,
        "chapters": chapters,
        "concepts": [dict(zip(("why", "why_ar"), concepts.why(concept)), **concept)
                     for concept in curriculum.get("concepts", [])],
    }


def latest_run() -> Path:
    runs = sorted(runio.RUNS_DIR.glob("run_*"))
    if not runs:
        raise SystemExit("no runs found in fixtures/runs")
    return runs[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", default="web/dist/site.html")
    args = parser.parse_args()

    run_dir = runio.RUNS_DIR / args.run_id if args.run_id else latest_run()
    payload = build_payload(run_dir)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    page = template.replace("__FONTS__", FONTS_PATH.read_text(encoding="utf-8"))
    page = page.replace("__STYLE__", STYLE_PATH.read_text(encoding="utf-8"))
    page = page.replace("__DATA__", json.dumps(payload, ensure_ascii=False))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} from {run_dir.name}")


if __name__ == "__main__":
    main()
