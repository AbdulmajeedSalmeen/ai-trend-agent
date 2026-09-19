import argparse
import json
from pathlib import Path

from src import runio
from src.schema import Recommendation, Score, Signal, Trend

CURRICULUM_PATH = Path("fixtures/curriculum.json")
TEMPLATE_PATH = Path("src/site_template.html")
FONTS_PATH = Path("src/site_fonts.css")
STYLE_PATH = Path("src/site_style.css")


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


def build_payload(run_dir: Path) -> dict:
    artifacts = read_run(run_dir)
    curriculum = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))

    signals = {s.id: s for s in artifacts["signals"]}
    scores = {s.trend_id: s for s in artifacts["scores"]}
    trends = {t.id: t for t in artifacts["trends"]}

    sources = {}
    for signal in artifacts["signals"]:
        sources[signal.source] = sources.get(signal.source, 0) + 1

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
        items.append(
            {
                "trend_id": trend.id,
                "subject": trend.subject,
                "family": trend.subject.replace("_", "-").split("-")[0],
                "action": rec.action,
                "chapter_id": rec.chapter_id,
                "rationale": rec.rationale,
                "chapter_version": rec.chapter_version,
                "latest_version": rec.latest_version,
                "gap_kind": rec.gap_kind,
                "releases_since": rec.releases_since,
                "priority": round(score.priority, 2),
                "confidence": round(score.confidence, 2),
                "dimensions": score.dimensions,
                "provenance": score.provenance,
                "signal_count": len(trend.signal_ids),
                "confirmed": confirmed,
                "unverified": len(claims) - confirmed,
                "claims": claims,
            }
        )

    items.sort(key=lambda i: (-i["priority"], i["subject"]))

    all_claims = [c for i in items for c in i["claims"]]
    kinds = {"cross_source": 0, "primary_report": 0, "unverified": 0}
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
                "pins": chapter.get("pins", {}),
                "last_updated": chapter.get("last_updated"),
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
            "watch": sum(1 for i in items if i["action"] == "watch"),
            "kinds": kinds,
            "chapters": len(chapters),
            "chapters_touched": len({i["chapter_id"] for i in items if i["chapter_id"]}),
        },
        "items": items,
        "chapters": chapters,
    }


def latest_run() -> Path:
    runs = sorted(runio.RUNS_DIR.glob("run_*"))
    if not runs:
        raise SystemExit("no runs found in fixtures/runs")
    return runs[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", default="web/site.html")
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
