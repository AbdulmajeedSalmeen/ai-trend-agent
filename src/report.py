import argparse
import html
import json
from collections import defaultdict
from pathlib import Path

from src import runio
from src.schema import Recommendation, Score, Signal, Trend

CURRICULUM_PATH = Path("fixtures/curriculum.json")

ACTION_LABELS = {
    "update_existing_material": "Update existing material",
    "add_new_lesson": "Add a new lesson",
    "watch": "Watch only",
}

STYLE = """
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; font: 15px/1.55 system-ui, sans-serif; color: #1c2024; background: #f7f8fa; }
.wrap { max-width: 960px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 32px 0 12px; }
.sub { color: #6b7280; font-size: 13px; margin-bottom: 24px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
.card { flex: 1 1 130px; background: #fff; border: 1px solid #e3e6ea; border-radius: 10px; padding: 12px 14px; }
.card .n { font-size: 22px; font-weight: 600; }
.card .l { color: #6b7280; font-size: 12px; }
.chapter { background: #fff; border: 1px solid #e3e6ea; border-radius: 10px; padding: 14px 16px; margin-bottom: 10px; }
.chapter h3 { margin: 0 0 2px; font-size: 15px; }
.topics { color: #6b7280; font-size: 12px; margin-bottom: 10px; }
.rec { border-top: 1px solid #eef0f3; padding: 10px 0 2px; }
.rec:first-of-type { border-top: 0; }
.subject { font-weight: 600; }
.rationale { color: #4b5563; font-size: 13px; margin: 4px 0 6px; }
.tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 999px; margin-right: 6px; }
.update { background: #dcfce7; color: #166534; }
.add { background: #fef3c7; color: #92400e; }
.watch { background: #e5e7eb; color: #374151; }
.confirmed { background: #dbeafe; color: #1e40af; }
.unverified { background: #fee2e2; color: #991b1b; }
.claims { font-size: 12px; color: #4b5563; margin: 0; padding-left: 18px; }
.claims a { color: #2563eb; text-decoration: none; }
.gap { border-left: 3px solid #f59e0b; }
.empty { color: #9ca3af; font-size: 13px; }
"""


def load_curriculum() -> dict:
    return json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))


def read_run(run_dir: Path) -> dict:
    out = {}
    for name, model in [
        ("signals", Signal),
        ("trends", Trend),
        ("scores", Score),
        ("recommendations", Recommendation),
    ]:
        path = run_dir / f"{name}.json"
        out[name] = runio.load_artifact(run_dir, name, model) if path.exists() else []
    return out


def action_class(action: str) -> str:
    return {"update_existing_material": "update", "add_new_lesson": "add"}.get(action, "watch")


def claim_items(trend: Trend, limit: int = 4) -> str:
    rows = []
    for claim in trend.claims[:limit]:
        badge = f'<span class="tag {claim.verdict}">{claim.verdict}</span>'
        link = ""
        if claim.evidence_url:
            kind = claim.evidence_kind or "evidence"
            link = f' <a href="{html.escape(claim.evidence_url)}">{kind}</a>'
        rows.append(f"<li>{badge}{html.escape(claim.text)}{link}</li>")
    hidden = len(trend.claims) - limit
    if hidden > 0:
        rows.append(f'<li class="empty">+ {hidden} more claims</li>')
    return f'<ul class="claims">{"".join(rows)}</ul>'


def build_html(run_dir: Path) -> str:
    data = read_run(run_dir)
    curriculum = load_curriculum()
    trends = {t.id: t for t in data["trends"]}
    scores = {s.trend_id: s for s in data["scores"]}

    by_chapter = defaultdict(list)
    for rec in data["recommendations"]:
        by_chapter[rec.chapter_id].append(rec)

    claims = [c for t in data["trends"] for c in t.claims]
    confirmed = sum(1 for c in claims if c.verdict == "confirmed")
    cards = [
        (len(data["signals"]), "signals"),
        (len(data["trends"]), "trends"),
        (confirmed, "confirmed claims"),
        (len(claims) - confirmed, "unverified claims"),
        (len(data["recommendations"]), "recommendations"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="n">{n}</div><div class="l">{label}</div></div>'
        for n, label in cards
    )

    def rec_block(rec: Recommendation) -> str:
        trend = trends.get(rec.trend_id)
        score = scores.get(rec.trend_id)
        subject = trend.subject if trend else rec.trend_id
        priority = f"{score.priority:.2f}" if score else "-"
        return (
            f'<div class="rec">'
            f'<span class="tag {action_class(rec.action)}">{ACTION_LABELS.get(rec.action, rec.action)}</span>'
            f'<span class="subject">{html.escape(subject)}</span> '
            f'<span class="empty">priority {priority}</span>'
            f'<div class="rationale">{html.escape(rec.rationale)}</div>'
            f"{claim_items(trend) if trend else ''}"
            f"</div>"
        )

    chapters_html = []
    for chapter in curriculum["chapters"]:
        recs = by_chapter.get(chapter["chapter_id"], [])
        if not recs:
            continue
        topics = ", ".join(chapter["topics_covered"][:8])
        chapters_html.append(
            f'<div class="chapter"><h3>{chapter["chapter_id"]} · {html.escape(chapter["title"])}</h3>'
            f'<div class="topics">{html.escape(topics)}</div>'
            f'{"".join(rec_block(r) for r in recs)}</div>'
        )

    gaps = by_chapter.get(None, [])
    gaps_html = (
        f'<div class="chapter gap"><h3>Not covered by the curriculum</h3>'
        f'<div class="topics">No chapter teaches these, so they are candidates for a new lesson.</div>'
        f'{"".join(rec_block(r) for r in gaps)}</div>'
        if gaps
        else '<p class="empty">Every subject in this run maps to a chapter.</p>'
    )

    untouched = [
        c for c in curriculum["chapters"] if not by_chapter.get(c["chapter_id"])
    ]
    untouched_html = "".join(
        f'<div class="chapter"><h3>{c["chapter_id"]} · {html.escape(c["title"])}</h3>'
        f'<div class="topics">{html.escape(", ".join(c["topics_covered"][:8]))}</div>'
        f'<p class="empty">Nothing in this run touches this chapter.</p></div>'
        for c in untouched
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Trend Agent — {run_dir.name}</title>
<style>{STYLE}</style></head>
<body><div class="wrap">
<h1>Curriculum view</h1>
<div class="sub">{html.escape(curriculum["name"])} · run {run_dir.name}</div>
<div class="cards">{cards_html}</div>
<h2>Chapters with suggested changes</h2>
{"".join(chapters_html) or '<p class="empty">No recommendations in this run.</p>'}
<h2>Curriculum gaps</h2>
{gaps_html}
<h2>Chapters untouched by this run</h2>
{untouched_html or '<p class="empty">None.</p>'}
</div></body></html>
"""


def latest_run() -> Path:
    runs = sorted(runio.RUNS_DIR.glob("run_*"))
    if not runs:
        raise SystemExit("no runs found in fixtures/runs")
    return runs[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_dir = runio.RUNS_DIR / args.run_id if args.run_id else latest_run()
    output = run_dir / "report.html"
    output.write_text(build_html(run_dir), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
