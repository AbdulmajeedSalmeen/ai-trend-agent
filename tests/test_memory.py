import json

from src import memory


def make_run(root, run_id, recs):
    """recs: subject -> (action, latest_version)"""
    path = root / run_id
    path.mkdir(parents=True)
    trends = [{"id": f"t{i}", "subject": subject} for i, subject in enumerate(recs)]
    (path / "trends.json").write_text(json.dumps(trends), encoding="utf-8")
    (path / "recommendations.json").write_text(json.dumps([
        {"trend_id": f"t{i}", "action": action, "latest_version": version}
        for i, (action, version) in enumerate(recs.values())
    ]), encoding="utf-8")
    return path


def test_only_runs_before_this_one_are_history(tmp_path):
    make_run(tmp_path, "run_20260901T000000Z", {})
    make_run(tmp_path, "run_20260910T000000Z", {})
    make_run(tmp_path, "run_20260920T000000Z", {})

    names = [p.name for p in memory.earlier_runs("run_20260910T000000Z", tmp_path)]

    assert names == ["run_20260901T000000Z"]


def test_history_is_newest_first(tmp_path):
    make_run(tmp_path, "run_20260901T000000Z", {})
    make_run(tmp_path, "run_20260910T000000Z", {})

    names = [p.name for p in memory.earlier_runs("run_20260920T000000Z", tmp_path)]

    assert names == ["run_20260910T000000Z", "run_20260901T000000Z"]


def test_an_unfinished_run_contributes_nothing(tmp_path):
    (tmp_path / "run_20260901T000000Z").mkdir(parents=True)

    assert memory.recommendations_of(tmp_path / "run_20260901T000000Z") == {}


def test_a_subject_asked_about_three_runs_running_has_a_streak(tmp_path):
    for run_id in ["run_20260901T000000Z", "run_20260908T000000Z", "run_20260915T000000Z"]:
        make_run(tmp_path, run_id, {"langchain": ("update_existing_material", "1.4.2")})

    past = memory.history("run_20260922T000000Z", tmp_path)

    assert past["langchain"]["runs"] == 3
    assert past["langchain"]["first_run"] == "run_20260901T000000Z"


def test_watching_breaks_the_streak(tmp_path):
    make_run(tmp_path, "run_20260901T000000Z", {"langchain": ("update_existing_material", "1.4.0")})
    make_run(tmp_path, "run_20260908T000000Z", {"langchain": ("watch", "1.4.1")})
    make_run(tmp_path, "run_20260915T000000Z", {"langchain": ("update_existing_material", "1.4.2")})

    assert memory.history("run_20260922T000000Z", tmp_path)["langchain"]["runs"] == 1


def test_a_subject_we_have_never_reported_is_new():
    assert memory.recall("crewai", "add_new_lesson", "1.0.0", {}) == {
        "runs_flagged": 1, "first_seen_run": None, "version_moved": False
    }


def test_a_repeat_counts_this_run_too(tmp_path):
    for run_id in ["run_20260901T000000Z", "run_20260908T000000Z"]:
        make_run(tmp_path, run_id, {"langchain": ("update_existing_material", "1.4.2")})

    past = memory.history("run_20260922T000000Z", tmp_path)
    recalled = memory.recall("langchain", "update_existing_material", "1.4.2", past)

    assert recalled["runs_flagged"] == 3
    assert recalled["version_moved"] is False


def test_a_new_version_since_last_time_is_noticed(tmp_path):
    make_run(tmp_path, "run_20260915T000000Z", {"langchain": ("update_existing_material", "1.4.1")})

    past = memory.history("run_20260922T000000Z", tmp_path)

    assert memory.recall("langchain", "update_existing_material", "1.4.2", past)["version_moved"]


def test_watching_now_does_not_claim_a_streak(tmp_path):
    make_run(tmp_path, "run_20260915T000000Z", {"langchain": ("update_existing_material", "1.4.2")})

    past = memory.history("run_20260922T000000Z", tmp_path)

    assert memory.recall("langchain", "watch", "1.4.2", past)["runs_flagged"] == 1


def test_history_stops_at_the_lookback_limit(tmp_path):
    for day in range(1, 12):
        make_run(tmp_path, f"run_202609{day:02d}T000000Z",
                 {"langchain": ("update_existing_material", "1.4.2")})

    past = memory.history("run_20260930T000000Z", tmp_path, limit=4)

    assert past["langchain"]["runs"] == 4
