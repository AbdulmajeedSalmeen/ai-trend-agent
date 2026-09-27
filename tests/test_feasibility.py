import re
from datetime import datetime, timezone

from src import feasibility, gap, plan
from src.schema import Score
from src.sources.pypi import summarise
from src.stages.stage4_act import closing_for, decide_action
from tests.test_arabic import same_numbers

AS_OF = datetime(2026, 9, 22, tzinfo=timezone.utc)
DASH = re.compile("[–—]")


def facts(first="2022-10-01T00:00:00+00:00", stable="1.4.2", requires=()):
    return {"pypi": "tool", "first_release": first, "latest_stable": stable, "requires": list(requires)}


def test_an_old_stable_steady_tool_is_fully_mature():
    score, source, detail = feasibility.maturity(facts(), AS_OF, {"feature": 3}, "1.4.2")

    assert (score, source) == (5, "measured")
    assert detail["age_years"] == 4.0 and detail["major"] == 1 and detail["steady"]


def test_a_tool_with_only_pre_releases_and_days_of_history_is_not_ready_to_teach():
    score, _, _ = feasibility.maturity(facts(first="2026-09-18T00:00:00+00:00", stable=None), AS_OF, {}, "0.0.1a3")

    assert score == 1


def test_a_breaking_change_in_the_run_costs_one_point_of_maturity():
    steady, _, _ = feasibility.maturity(facts(), AS_OF, {}, "1.4.2")
    moving, _, _ = feasibility.maturity(facts(), AS_OF, {"breaking": 2}, "1.4.2")

    assert steady - moving == 1


def test_without_a_pypi_history_maturity_is_a_default_not_a_guess():
    assert feasibility.maturity(None, AS_OF, {}, "1.0.0") == (3, "default", {})


def test_prerequisites_follow_what_the_course_teaches():
    taught = {"langchain", "openai"}

    assert feasibility.prerequisites("langchain", None, taught)[:2] == (5, "measured")
    assert feasibility.prerequisites("langchain-core", None, taught)[2] == {"basis": "family", "via": ["langchain"]}
    assert feasibility.prerequisites("crewai", facts(requires=["openai", "pydantic"]), taught)[2]["via"] == ["openai"]


def test_no_link_to_the_course_is_left_unmeasured_rather_than_called_a_gap():
    assert feasibility.prerequisites("anthropic-sdk-python", facts(requires=["httpx"]), {"openai"}) == \
        (3, "default", {})


def test_difficulty_grows_with_the_lines_to_change_and_how_far_they_reach():
    many = [{"chapter_id": f"C{index % 11 + 8}"} for index in range(85)]

    assert feasibility.difficulty("C8", {}, [], 4)[0] == 1
    assert feasibility.difficulty("C8", {}, many[:3], 4)[0] == 3
    assert feasibility.difficulty("C8", {}, many, 4)[0] == 4
    assert feasibility.difficulty("C8", {"breaking": 1}, many, 4)[0] == 5


def test_new_material_starts_at_three_and_costs_more_on_a_tool_still_settling():
    assert feasibility.difficulty(None, {}, [], 4)[0] == 3
    assert feasibility.difficulty(None, {}, [], 2)[0] == 4


def test_feasibility_is_the_mean_of_maturity_prerequisites_and_ease():
    assert feasibility.score({"maturity": 4, "prerequisites": 5, "difficulty": 4}) == round((4 + 5 + 2) / 3, 1)
    assert feasibility.score({"maturity": 4}) is None


def test_every_factor_explains_itself_with_the_same_figures_in_both_languages():
    cases = [
        ("maturity", *feasibility.maturity(facts(), AS_OF, {}, "1.4.2")),
        ("maturity", 3, "default", {}),
        ("prerequisites", *feasibility.prerequisites("crewai", facts(requires=["openai"]), {"openai"})),
        ("prerequisites", 3, "default", {}),
        ("difficulty", *feasibility.difficulty("C8", {"breaking": 2}, [{"chapter_id": "C8"}] * 2, 4)),
        ("difficulty", *feasibility.difficulty("C8", {}, [], 4)),
        ("difficulty", *feasibility.difficulty(None, {}, [], 1)),
    ]

    for factor, value, source, detail in cases:
        english, arabic_reason = feasibility.explain(factor, value, source, detail, "crewai")

        assert same_numbers(english, arabic_reason), (english, arabic_reason)
        assert re.search("[؀-ۿ]", arabic_reason)
        assert not DASH.search(english + arabic_reason)


def test_pypi_history_skips_yanked_files_pre_releases_and_optional_extras():
    payload = {
        "releases": {
            "0.1.0": [{"upload_time_iso_8601": "2021-01-05T00:00:00Z", "yanked": True}],
            "0.2.0": [{"upload_time_iso_8601": "2022-03-01T00:00:00Z"}],
            "1.0.0": [{"upload_time_iso_8601": "2024-01-01T00:00:00Z"}],
            "1.1.0b1": [{"upload_time_iso_8601": "2026-09-01T00:00:00Z"}],
        },
        "info": {"requires_dist": ["openai>=1.0", "pydantic (>=2)", "rich ; extra == 'cli'", "openai<3"]},
    }

    summary = summarise("tool", payload)

    assert summary["first_release"].startswith("2022-03-01")
    assert summary["latest_stable"] == "1.0.0"
    assert summary["requires"] == ["openai", "pydantic"]


def scored(maturity, provenance="measured", chapter_id="C8"):
    return Score(trend_id="t", chapter_id=chapter_id, confidence=0.9, priority=3.4,
                 dimensions={"relevance": 5, "market_relevance": 4, "maturity": maturity},
                 provenance={"market_relevance": "measured", "maturity": provenance},
                 changes={"feature": 3, "highlights": ["feature: add something"]})


def assessment(kind, legacy=()):
    return {"subject": "tool", "pinned": None, "latest": "0.0.1a3", "kind": kind, "chapter_updated": "2026-08-27",
            "released_since": 5, "sentence": "", "legacy": list(legacy)}


def test_a_tool_not_stable_enough_to_teach_is_watched_with_that_reason():
    unknown = assessment(gap.UNKNOWN)

    assert decide_action(scored(1), unknown) == "watch"
    assert closing_for(scored(1), "watch", unknown) == "immature"
    assert decide_action(scored(1, chapter_id=None)) == "watch"


def test_an_immature_tool_whose_old_imports_break_the_notebook_is_still_fixed():
    broken = assessment(gap.UNPINNED, legacy=[{"uses": "RetrievalQA", "verified": True}])

    assert decide_action(scored(1), broken) == "update_existing_material"


def test_an_unmeasured_maturity_never_gates_a_decision():
    assert decide_action(scored(1, provenance="default"), assessment(gap.UNKNOWN)) == "update_existing_material"


def test_the_plan_for_an_immature_tool_says_when_to_look_again():
    steps, steps_ar = plan.build("tool", scored(1), "watch", assessment(gap.UNKNOWN), [])

    assert steps[0] == "Revisit once tool has a stable release and a year of history."
    assert steps_ar[0] == "أعد النظر حين يصدر tool إصداراً مستقراً ويمضي على أول إصدار له عام."
