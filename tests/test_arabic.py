import itertools
import re
import shutil
from collections import Counter
from pathlib import Path

from src import arabic, gap, plan, runio
from src.schema import Claim, Recommendation, Score, Signal, Trend
from src.stages import stage4_act
from src.stages.stage4_act import build_rationale, course_edits, decide, decide_action, load_chapters, redecide

FROZEN = Path("fixtures/runs/run_20260922T102800Z")

# A version, a date, a priority, a compact install count, or a plain count.
NUMBER = re.compile(r"\d+(?:[.\-]\d+)*(?:[A-Za-z]+\d*)?")
# Arabic writes one and two as words, and no job posts at all as a sentence.
SPELLED_OUT = {"0", "1", "2"}
DASH = re.compile("[–—]")
ARABIC_LETTER = re.compile("[؀-ۿ]")
LATIN_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.\-][A-Za-z0-9]+)*")
ENGLISH_WORDING = re.compile(r"\b(confirmed|unverified|priority|chapter|releases|installs|job posts?)\b", re.I)


def same_numbers(english: str, arabic_reason: str) -> bool:
    """Every figure in the English is in the Arabic, as many times, except the
    ones Arabic spells out."""
    en = Counter(NUMBER.findall(english))
    ar = Counter(NUMBER.findall(arabic_reason))
    spelled = all(ar[n] <= en[n] for n in SPELLED_OUT)

    for n in SPELLED_OUT:
        en.pop(n, None)
        ar.pop(n, None)

    return spelled and en == ar


def frozen_reasons():
    """Both languages' rules reason for every card in the frozen run, decided the
    way stage 4 decides it."""
    trends = {trend.id: trend for trend in runio.load_artifact(FROZEN, "trends", Trend)}
    scores = {score.trend_id: score for score in runio.load_artifact(FROZEN, "scores", Score)}
    signals = runio.load_artifact(FROZEN, "signals", Signal)
    published = {signal.id: signal.published_at.isoformat() for signal in signals}
    chapters = load_chapters()
    edits_by_package = course_edits(chapters)

    for rec in runio.load_artifact(FROZEN, "recommendations", Recommendation):
        trend, score = trends[rec.trend_id], scores[rec.trend_id]
        decided = decide(trend, score, chapters, published, edits_by_package)
        facts = (trend, score, decided["action"], decided["assessment"], decided["chapter"])
        yield (trend.subject,
               build_rationale(*facts, edits=decided["edits"]),
               build_rationale(*facts, lang="ar", edits=decided["edits"]))


def test_counts_agree_with_their_noun_the_way_arabic_requires():
    assert arabic.counted(1, arabic.JOB) == "وظيفة واحدة"
    assert arabic.counted(2, arabic.JOB) == "وظيفتان"
    assert arabic.counted(3, arabic.JOB) == "3 وظائف"
    assert arabic.counted(10, arabic.JOB) == "10 وظائف"
    assert arabic.counted(11, arabic.JOB) == "11 وظيفة"
    assert arabic.counted(99, arabic.JOB) == "99 وظيفة"
    assert arabic.counted(100, arabic.JOB) == "100 وظيفة"
    assert arabic.counted(103, arabic.JOB) == "103 وظائف"
    assert arabic.counted(114, arabic.JOB) == "114 وظيفة"


def test_two_job_posts_take_the_dual_verb():
    found = {"jobs": 2, "job_term": "langsmith", "months": 3}

    assert arabic.market_sentence(found, "langsmith", None, True) == "وظيفتان ذكرتا langsmith في آخر 3 أشهر."
    assert arabic.market_sentence(found | {"jobs": 14}, "langsmith", None, True) == \
        "14 وظيفة ذكرت langsmith في آخر 3 أشهر."


def test_releases_since_the_last_update_read_as_one_sentence_whatever_the_count():
    def stale(since):
        return arabic.staleness_sentence({"released_since": since, "chapter_updated": "2026-08-27"})

    assert stale(1) == "صدرت نسخة مؤكدة واحدة بعد آخر تحديث للفصل في 2026-08-27."
    assert stale(2) == "صدرت نسختان مؤكدتان بعد آخر تحديث للفصل في 2026-08-27."
    assert stale(13) == "صدرت 13 نسخة مؤكدة بعد آخر تحديث للفصل في 2026-08-27."
    assert stale(0) == ""


SUBJECT = "langchain"
UPDATED = "2026-08-27"
LEGACY = [
    {"package": SUBJECT, "uses": "LLMChain", "note": "removed in langchain 1.x, replaced by the LCEL pipe"},
    {"package": SUBJECT, "uses": "langchain.chains imports", "note": "most of it moved to langchain-classic in 1.x"},
    {"package": SUBJECT, "uses": "load_qa_chain", "note": "removed in langchain 1.x"},
]
# pinned, installed without a bound, taught, has a chapter
SITUATIONS = [
    ("1.4.2", False, True, True),
    ("1.5.0", False, True, True),
    ("1.4.0", False, True, True),
    ("1.3.0", False, True, True),
    ("0.1.0", False, True, True),
    (None, True, True, True),
    (None, True, False, True),
    (None, False, True, True),
    (None, False, True, False),
]
CHANGES = [
    {},
    {"breaking": 1, "highlights": ["breaking: drop Python 3.9 support"]},
    {"breaking": 14, "feature": 3, "highlights": ["breaking: remove v1 routes", "feature: add streaming 2.0"]},
    {"deprecation": 2, "highlights": ["deprecation: deprecate group_type"]},
    {"feature": 2},
    {"feature": 36, "highlights": ["feature: add 12 new providers"]},
    {"fix": 3, "noise": 2},
    {"fix": 1, "noise": 11},
    {"fix": 0, "noise": 4},
]
MARKETS = [
    {},
    {"jobs": 0, "job_term": SUBJECT, "downloads": 3_500_000, "months": 3},
    {"jobs": 1, "job_term": SUBJECT, "downloads": None, "months": 3},
    {"jobs": 2, "job_term": SUBJECT, "downloads": 863_000, "months": 3},
    {"jobs": 17, "job_term": SUBJECT, "downloads": 176_700_000, "months": 3},
    {"jobs": None, "downloads": 1_400},
]


def every_card():
    """A card for every gap kind, legacy list, change, market, confidence and
    staleness the rules can meet, decided the way stage 4 decides it."""
    chapter = load_chapters()["C8"]
    claims = [Claim(text=f"{SUBJECT} version 1.4.2 was released", subject=SUBJECT, version="1.4.2",
                    verdict="confirmed", confidence=0.9) for _ in range(12)]
    claims.append(Claim(text=f"{SUBJECT} 1.5 is coming", subject=SUBJECT))
    trend = Trend(id="trend_001", subject=SUBJECT, signal_ids=["gh_1"], claims=claims)

    for situation, legacy, changes, market, confidence, since in itertools.product(
            SITUATIONS, ([], LEGACY[:1], LEGACY), CHANGES, MARKETS, (0.9, 0.4), (0, 1, 2, 13)):
        pinned, unpinned, taught, has_chapter = situation
        published = ["2026-09-01T00:00:00+00:00"] * since + ["2026-08-01T00:00:00+00:00"]
        assessment = gap.assess(SUBJECT, ["1.4.2", "1.4.1"], pinned, published, UPDATED,
                                unpinned=unpinned, legacy=legacy if has_chapter else [],
                                has_chapter=has_chapter, taught=taught)
        wanted = 4 if (market.get("jobs") or 0) >= 5 else 2
        score = Score(
            trend_id=trend.id, chapter_id="C8" if has_chapter else None, confidence=confidence,
            dimensions={"relevance": 4, "market_relevance": wanted},
            provenance={"relevance": "measured", "market_relevance": "measured" if market else "unmeasured"},
            priority=3.4, changes=changes, market=market,
        )
        action = decide_action(score, assessment)
        card = chapter if has_chapter else None
        steps, steps_ar = plan.build(SUBJECT, score, action, assessment, [])

        yield (build_rationale(trend, score, action, assessment, card),
               build_rationale(trend, score, action, assessment, card, lang="ar"), steps, steps_ar)


# The page sets each step on a line of its own.
STEP_LIMIT = 160


def test_the_arabic_reason_never_says_a_figure_the_english_does_not():
    checked = 0

    for english, arabic_reason, _, _ in every_card():
        assert same_numbers(english, arabic_reason), (english, arabic_reason)
        assert SUBJECT in arabic_reason
        assert not DASH.search(arabic_reason), arabic_reason
        assert not ENGLISH_WORDING.search(arabic_reason), arabic_reason
        checked += 1

    assert checked > 10_000


def test_every_plan_has_the_same_steps_and_figures_in_both_languages():
    for _, _, steps, steps_ar in every_card():
        assert 2 <= len(steps) == len(steps_ar) <= 3, steps

        for step, step_ar in zip(steps, steps_ar):
            assert same_numbers(step, step_ar), (step, step_ar)
            assert ARABIC_LETTER.search(step_ar), step_ar
            assert not DASH.search(step + step_ar), step
            assert len(step) <= STEP_LIMIT and len(step_ar) <= STEP_LIMIT, (step, step_ar)


def test_every_card_in_the_frozen_run_carries_the_same_figures_in_both_languages():
    reasons = list(frozen_reasons())

    assert len(reasons) == 37

    for subject, english, arabic_reason in reasons:
        assert same_numbers(english, arabic_reason), subject
        assert subject in arabic_reason
        assert ARABIC_LETTER.search(arabic_reason), subject
        assert not DASH.search(arabic_reason), subject


def test_every_pattern_table_note_in_the_curriculum_has_its_arabic():
    notes = {marker["note"] for chapter in load_chapters().values()
             for marker in chapter.get("legacy_api", [])}

    assert notes <= set(arabic.NOTES)


def test_no_arabic_wording_uses_a_long_dash():
    wording = [*arabic.NOTES.values(), arabic.GENERIC_NOTE, *arabic.CLOSINGS.values(), *arabic.USES.values()]

    assert not [text for text in wording if DASH.search(text)]


def test_every_chapter_says_what_it_teaches_in_arabic_without_inventing_a_name():
    chapters = load_chapters()

    assert len(chapters) == 25

    for chapter_id, chapter in chapters.items():
        teaches_ar = chapter.get("teaches_ar") or ""

        assert ARABIC_LETTER.search(teaches_ar), chapter_id
        assert not DASH.search(teaches_ar), chapter_id

        for name in LATIN_NAME.findall(teaches_ar):
            assert name in chapter["teaches"], (chapter_id, name)


def copy_of_frozen_run(tmp_path) -> Path:
    run_dir = tmp_path / FROZEN.name
    run_dir.mkdir()

    for name in ("signals", "trends", "scores", "recommendations"):
        shutil.copy(FROZEN / f"{name}.json", run_dir / f"{name}.json")

    return run_dir


def refuse(*args, **kwargs):
    raise AssertionError("the Arabic reason asked the model")


def test_redeciding_a_saved_run_asks_no_model_and_keeps_what_it_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr("src.adapters.model.ask_json", refuse)
    run_dir = copy_of_frozen_run(tmp_path)
    before = {rec.trend_id: rec for rec in runio.load_artifact(run_dir, "recommendations", Recommendation)}

    redecide(run_dir)
    after = runio.load_artifact(run_dir, "recommendations", Recommendation)

    assert len(after) == 37
    for rec in after:
        old = before[rec.trend_id]
        assert (rec.runs_flagged, rec.first_seen_run, rec.version_moved) == \
            (old.runs_flagged, old.first_seen_run, old.version_moved)
        assert ARABIC_LETTER.search(rec.rationale_ar)
        assert 2 <= len(rec.action_plan) == len(rec.action_plan_ar) <= 3

        if rec.action == old.action:
            assert rec.rationale == old.rationale


def test_when_the_model_writes_the_english_the_arabic_is_still_the_rules(tmp_path, monkeypatch):
    run_dir = copy_of_frozen_run(tmp_path)
    monkeypatch.setattr(stage4_act, "write_recommendation", lambda *args, **kwargs: "A model wrote this.")
    monkeypatch.setattr(stage4_act.memory, "history", lambda *args, **kwargs: {})

    stage4_act.run(run_dir)
    written = runio.load_artifact(run_dir, "recommendations", Recommendation)
    rules = {subject: arabic_reason for subject, _, arabic_reason in frozen_reasons()}
    subjects = {trend.id: trend.subject for trend in runio.load_artifact(run_dir, "trends", Trend)}

    assert {rec.rationale for rec in written} == {"A model wrote this."}
    for rec in written:
        assert rec.rationale_ar == rules[subjects[rec.trend_id]]
