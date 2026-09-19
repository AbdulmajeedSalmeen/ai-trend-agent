from src import gap


def test_a_version_with_no_numbers_has_no_parts():
    assert gap.parts("latest") is None


def test_a_pre_release_keeps_its_numbers():
    assert gap.parts("0.0.1a2") == (0, 0, 1)


def test_newest_compares_numbers_not_text():
    assert gap.newest(["1.9.0", "1.10.0", "1.2.11"]) == "1.10.0"


def test_newest_ignores_claims_without_a_version():
    assert gap.newest([None, "0.3.1", None]) == "0.3.1"


def test_newest_of_nothing_is_none():
    assert gap.newest([None, "unreleased"]) is None


def test_an_unrecorded_chapter_version_gives_unknown():
    assert gap.compare(None, "1.4.2") == gap.UNKNOWN


def test_three_patch_releases_are_not_a_reason_to_rewrite():
    assert gap.compare("1.4.0", "1.4.2") == gap.PATCH_ONLY


def test_a_minor_release_is_actionable():
    assert gap.compare("1.4.0", "1.6.2") == gap.BEHIND_MINOR


def test_a_major_release_is_actionable():
    assert gap.compare("0.1.0", "1.4.2") == gap.BEHIND_MAJOR


def test_the_same_version_is_current():
    assert gap.compare("1.4.2", "1.4.2") == gap.CURRENT


def test_a_chapter_ahead_of_the_run_is_not_behind():
    assert gap.compare("2.0.0", "1.4.2") == gap.AHEAD


def test_a_short_version_is_padded_before_comparing():
    assert gap.compare("1.4", "1.4.0") == gap.CURRENT


def test_only_actionable_kinds_justify_a_rewrite():
    assert gap.ACTIONABLE == {gap.BEHIND_MAJOR, gap.BEHIND_MINOR}


def test_the_sentence_names_both_versions():
    sentence = gap.describe("langchain", "0.1.0", "1.4.2", gap.BEHIND_MAJOR)

    assert "0.1.0" in sentence and "1.4.2" in sentence and "major" in sentence


def test_the_sentence_admits_when_the_chapter_records_nothing():
    sentence = gap.describe("langchain", None, "1.4.2", gap.UNKNOWN)

    assert "does not record" in sentence


def test_releases_before_the_chapter_was_updated_do_not_count():
    dates = ["2026-08-01T00:00:00Z", "2026-09-10T00:00:00Z", "2026-09-18T00:00:00Z"]

    assert gap.count_after(dates, "2026-08-27") == 2


def test_nothing_counts_when_the_chapter_has_no_date():
    assert gap.count_after(["2026-09-18T00:00:00Z"], None) == 0


def test_an_assessment_reports_both_the_version_and_the_date_gap():
    assessment = gap.assess(
        "langchain", ["1.4.0", "1.4.2", None], "0.1.0",
        ["2026-09-18T00:00:00Z", "2026-09-17T00:00:00Z"], "2026-08-27",
    )

    assert assessment["latest"] == "1.4.2"
    assert assessment["kind"] == gap.BEHIND_MAJOR
    assert assessment["released_since"] == 2


def test_the_staleness_sentence_is_empty_when_nothing_is_newer():
    assessment = gap.assess("langchain", ["1.4.2"], None, [], "2026-08-27")

    assert gap.staleness_sentence(assessment) == ""


def test_the_staleness_sentence_counts_what_landed_after():
    assessment = gap.assess("langchain", ["1.4.2"], None, ["2026-09-18T00:00:00Z"], "2026-08-27")

    assert "1 of the confirmed releases in this run landed after" in gap.staleness_sentence(assessment)
