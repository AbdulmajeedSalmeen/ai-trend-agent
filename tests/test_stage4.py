from src.schema import Score
from src.stages.stage4_act import decide_action


def make_score(**overrides):
    data = dict(
        trend_id="trend_001",
        chapter_id="C6",
        confidence=0.9,
        dimensions={"relevance": 4},
        provenance={"relevance": "measured"},
        priority=3.2,
    )
    data.update(overrides)
    return Score(**data)


def test_low_confidence_is_watched_even_at_high_priority():
    score = make_score(confidence=0.4, priority=4.0)

    assert decide_action(score) == "watch"


def test_high_priority_with_a_matching_chapter_updates_it():
    score = make_score(priority=3.2, chapter_id="C6")

    assert decide_action(score) == "update_existing_material"


def test_no_matching_chapter_becomes_a_new_lesson():
    score = make_score(priority=2.7, chapter_id=None)

    assert decide_action(score) == "add_new_lesson"


def test_low_priority_is_only_watched():
    score = make_score(priority=2.0, chapter_id="C6")

    assert decide_action(score) == "watch"

from src import gap
from src.stages.stage4_act import build_rationale
from src.schema import Claim, Trend


def make_assessment(kind, released_since=0, pinned="1.4.0", latest="1.4.2"):
    return {
        "subject": "langchain", "pinned": pinned, "latest": latest, "kind": kind,
        "chapter_updated": "2026-08-27", "released_since": released_since,
        "sentence": gap.describe("langchain", pinned, latest, kind), "legacy": [],
    }


def test_patch_releases_alone_never_rewrite_a_chapter():
    score = make_score(priority=4.0, chapter_id="C8")

    assert decide_action(score, make_assessment(gap.PATCH_ONLY)) == "watch"


def test_a_major_release_rewrites_the_chapter():
    score = make_score(priority=3.2, chapter_id="C8")

    assert decide_action(score, make_assessment(gap.BEHIND_MAJOR, pinned="0.1.0")) == "update_existing_material"


def test_a_chapter_already_on_the_newest_version_is_left_alone():
    score = make_score(priority=4.0, chapter_id="C8")

    assert decide_action(score, make_assessment(gap.CURRENT)) == "watch"


def test_an_unrecorded_chapter_version_falls_back_to_how_much_landed_since():
    score = make_score(priority=3.2, chapter_id="C8")
    quiet = make_assessment(gap.UNKNOWN, released_since=1, pinned=None)
    busy = make_assessment(gap.UNKNOWN, released_since=5, pinned=None)

    assert decide_action(score, quiet) == "watch"
    assert decide_action(score, busy) == "update_existing_material"


def test_the_rationale_says_what_the_chapter_teaches_and_what_moved():
    trend = Trend(
        id="trend_007", subject="langchain", signal_ids=["gh_1"],
        claims=[Claim(text="langchain version 1.4.2 was released", subject="langchain",
                      version="1.4.2", verdict="confirmed", confidence=0.9)],
    )
    chapter = {"chapter_id": "C8", "teaches": "Rebuild document QA on LangChain."}
    assessment = make_assessment(gap.BEHIND_MAJOR, released_since=4, pinned="0.1.0")

    rationale = build_rationale(trend, make_score(chapter_id="C8"), "update_existing_material",
                                assessment, chapter)

    assert "Rebuild document QA on LangChain." in rationale
    assert "0.1.0 to 1.4.2" in rationale
    assert "4 of the confirmed releases in this run landed after" in rationale


from src.stages.stage4_act import change_sentence, market_sentence, readable


def measured_score(chapter_id="C8", market_relevance=4, changes_found=None, market=None, **extra):
    return make_score(
        chapter_id=chapter_id, priority=extra.get("priority", 3.4),
        dimensions={"relevance": 4, "market_relevance": market_relevance},
        provenance={"relevance": "measured", "market_relevance": "measured"},
        changes=changes_found or {}, market=market or {},
    )


def test_a_new_lesson_needs_employers_to_ask_for_it():
    rarely_hired = measured_score(chapter_id=None, market_relevance=2,
                                  changes_found={"feature": 30, "fix": 10, "highlights": []})

    assert decide_action(rarely_hired) == "add_optional_content"


def test_a_tool_no_employer_asks_for_is_only_watched():
    unwanted = measured_score(chapter_id=None, market_relevance=1,
                              changes_found={"feature": 30, "highlights": []})

    assert decide_action(unwanted) == "watch"


def test_optional_content_still_needs_something_to_teach():
    maintenance = measured_score(chapter_id=None, market_relevance=2,
                                 changes_found={"fix": 9, "noise": 4, "highlights": []})

    assert decide_action(maintenance) == "watch"


def test_a_release_that_breaks_imports_in_several_chapters_is_one_decision_for_the_course():
    score = measured_score(changes_found={"feature": 2, "highlights": ["feature: add create_agent"]})
    assessment = make_assessment(gap.UNPINNED, pinned=None)

    assert decide_action(score, assessment, chapters_affected=11) == "investigate_larger_change"
    assert decide_action(score, assessment, chapters_affected=1) == "update_existing_material"
    assert decide_action(make_score(confidence=0.4), assessment, chapters_affected=11) == "watch"


from src import plan


def edit(chapter_id, notebook, runs_as_pinned, installs):
    return {"chapter_id": chapter_id, "notebook": notebook, "runs_as_pinned": runs_as_pinned, "installs": installs}


COURSE_EDITS = [
    edit("C8", "notebooks/week 3/qa.ipynb", False, "unpinned"),
    edit("C12", "notebooks/week 4/loop.ipynb", True, "0.3.*"),
    edit("C13", "notebooks/week 4/tools.ipynb", True, "0.3.*"),
]


def test_a_course_wide_plan_fixes_what_breaks_first_then_asks_for_one_decision():
    score = measured_score()
    assessment = make_assessment(gap.UNPINNED, pinned=None)

    steps, steps_ar = plan.build("langchain", score, "investigate_larger_change", assessment, COURSE_EDITS)

    assert steps == [
        "First fix what breaks on today's install: 1 import line in 1 notebook (C8).",
        "Decide once, for the whole course: stay on the langchain line 2 notebooks pin (0.3.*), or move to langchain 1.4.2.",
        "To move, change 3 import lines in 3 notebooks across 3 chapters; the edit list names each cell.",
    ]
    assert steps_ar[1] == ("قرّر مرة واحدة للمقرر كله: البقاء على خط langchain الذي يثبّته نوتبوكان (0.3.*)، "
                           "أو الانتقال إلى langchain 1.4.2.")
    assert steps_ar[2] == "للانتقال: تغيير 3 أسطر استيراد في 3 نوتبوكات من 3 فصول، وقائمة التعديلات تسمّي كل خلية."


def test_two_after_a_preposition_take_the_oblique_dual():
    two_broken = [edit("C8", "notebooks/a.ipynb", False, "unpinned"), edit("C12", "notebooks/b.ipynb", False, "unpinned")]
    _, steps_ar = plan.build("langchain", measured_score(), "investigate_larger_change",
                             make_assessment(gap.UNPINNED, pinned=None), two_broken)

    assert steps_ar[0] == "أصلح أولاً ما يتعطل عند التثبيت اليوم: سطرا استيراد في نوتبوكين (C8، C12)."


def test_the_rationale_of_a_course_wide_decision_says_how_far_it_reaches():
    trend = Trend(id="trend_007", subject="langchain", signal_ids=["gh_1"],
                  claims=[Claim(text="langchain version 1.4.2 was released", subject="langchain",
                                version="1.4.2", verdict="confirmed", confidence=0.9)])
    chapter = {"chapter_id": "C8", "teaches": "Rebuild document QA on LangChain.", "teaches_ar": "إعادة بناء."}
    facts = (trend, measured_score(), "investigate_larger_change", make_assessment(gap.UNPINNED, pinned=None), chapter)

    english = build_rationale(*facts, edits=COURSE_EDITS)
    arabic_reason = build_rationale(*facts, lang="ar", edits=COURSE_EDITS)

    assert "Across the course, 3 notebooks in 3 chapters import names that langchain 1.4.2 no longer has." in english
    assert "plan the move once, for the whole course" in english
    assert "يستوردها 3 نوتبوكات في 3 فصول" in arabic_reason


def test_a_new_lesson_is_recommended_when_employers_ask_and_there_is_something_to_teach():
    wanted = measured_score(chapter_id=None, market_relevance=4, priority=3.2,
                            changes_found={"feature": 5, "highlights": []})

    assert decide_action(wanted) == "add_new_lesson"


def test_no_new_lesson_for_a_package_whose_releases_only_fix_things():
    maintenance = measured_score(chapter_id=None, market_relevance=5,
                                 changes_found={"fix": 12, "noise": 30, "highlights": []})

    assert decide_action(maintenance) == "watch"


def test_unmeasured_market_does_not_block_a_new_lesson():
    unmeasured = make_score(chapter_id=None, priority=3.0,
                            dimensions={"market_relevance": 2},
                            provenance={"market_relevance": "default"})

    assert decide_action(unmeasured) == "add_new_lesson"


def test_an_unbound_taught_package_with_only_fixes_is_watched():
    score = measured_score(changes_found={"fix": 5, "noise": 12, "highlights": []})
    assessment = make_assessment(gap.UNPINNED, pinned=None)

    assert decide_action(score, assessment) == "watch"


def test_an_unbound_package_whose_notebooks_call_a_removed_api_is_still_rewritten():
    score = measured_score(changes_found={"fix": 5, "highlights": []})
    assessment = make_assessment(gap.UNPINNED, pinned=None)
    assessment["legacy"] = [{"package": "langchain", "uses": "RetrievalQA", "note": "removed"}]

    assert decide_action(score, assessment) == "update_existing_material"


def test_a_major_version_behind_is_rewritten_even_if_recent_releases_are_quiet():
    score = measured_score(changes_found={"fix": 2, "highlights": []})

    assert decide_action(score, make_assessment(gap.BEHIND_MAJOR, pinned="0.1.0")) == "update_existing_material"


def test_the_reason_names_the_new_features():
    score = measured_score(changes_found={"feature": 3, "highlights": [
        "feature: add durable execution", "feature: add streaming"]})

    assert change_sentence(score) == "The releases add 3 new features (add durable execution; add streaming)."


def test_the_reason_leads_with_a_breaking_change():
    score = measured_score(changes_found={"breaking": 1, "feature": 4, "highlights": [
        "breaking: remove the Completion class"]})

    assert change_sentence(score).startswith("The releases include 1 breaking change (remove")


def test_the_reason_says_plainly_when_there_is_nothing_to_teach():
    score = measured_score(changes_found={"fix": 5, "noise": 20, "highlights": []})

    assert change_sentence(score) == "The releases are maintenance only: 5 fixes and 20 chores, nothing new to teach."


def test_the_reason_quotes_employer_demand():
    score = measured_score(market={"jobs": 24, "downloads": 363_000_000, "job_term": "fastapi", "months": 3})

    assert market_sentence(score, "fastapi") == (
        "24 job posts named fastapi in the last 3 months and 363M installs last month.")


def test_the_reason_says_when_few_employers_ask():
    score = measured_score(market_relevance=2, market={"jobs": 4, "downloads": None,
                                                       "job_term": "crewai", "months": 3})

    assert market_sentence(score, "crewai").endswith("Few employers ask for it yet.")


def test_no_market_data_says_nothing_rather_than_guessing():
    assert market_sentence(measured_score(market={}), "x") == ""


def test_large_numbers_read_like_a_person_wrote_them():
    assert readable(363_095_875) == "363.1M"
    assert readable(6_453_644) == "6.5M"
    assert readable(1_200) == "1.2K"
    assert readable(40) == "40"


def test_a_version_alone_never_asks_for_a_rewrite():
    no_notes_read = make_score(chapter_id="C9", priority=3.4)
    assessment = make_assessment(gap.UNPINNED, pinned=None)

    assert decide_action(no_notes_read, assessment) == "watch"


def test_an_unbound_package_with_a_new_concept_is_worth_rewriting_for():
    score = make_score(chapter_id="C19", priority=3.4,
                       changes={"feature": 3, "highlights": ["feature: add durable execution"]})
    assessment = make_assessment(gap.UNPINNED, pinned=None)

    assert decide_action(score, assessment) == "update_existing_material"


def test_a_pinned_notebook_a_minor_version_behind_still_runs_and_is_watched():
    score = make_score(chapter_id="C4", priority=3.4)
    assessment = make_assessment(gap.BEHIND_MINOR, pinned="2.5.1", latest="2.14.0")

    assert decide_action(score, assessment) == "watch"


def test_a_minor_gap_with_a_breaking_change_in_the_notes_is_rewritten():
    score = make_score(chapter_id="C4", priority=3.4,
                       changes={"breaking": 2, "highlights": ["breaking: remove the old API"]})
    assessment = make_assessment(gap.BEHIND_MINOR, pinned="2.5.1", latest="2.14.0")

    assert decide_action(score, assessment) == "update_existing_material"


def test_a_major_gap_is_rewritten_even_with_no_notes():
    score = make_score(chapter_id="C8", priority=3.4)

    assert decide_action(score, make_assessment(gap.BEHIND_MAJOR, pinned="0.1.0")) == "update_existing_material"


def test_a_plan_never_asks_to_pin_a_pre_release():
    beta = measured_score(changes_found={"fix": 2, "highlights": []})
    assessment = make_assessment(gap.UNPINNED, pinned=None, latest="3.4.0b1")

    steps, steps_ar = plan.build("dspy", beta, "watch", assessment, [])

    assert steps[0] == "Pin dspy to its newest stable release in the install cell; 3.4.0b1 is a pre-release."
    assert steps_ar[0] == "ثبّت dspy على أحدث إصدار مستقر في خلية التثبيت، فـ3.4.0b1 إصدار تجريبي."
