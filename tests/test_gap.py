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
    assert gap.ACTIONABLE == {gap.BEHIND_MAJOR, gap.BEHIND_MINOR, gap.UNPINNED}


def test_an_unpinned_install_is_its_own_verdict():
    assert gap.compare("0.3.*", "1.4.2", unpinned=True) == gap.UNPINNED


def test_the_unpinned_sentence_names_what_a_student_gets_today():
    sentence = gap.describe("langchain", None, "1.4.2", gap.UNPINNED)

    assert "no version bound" in sentence and "1.4.2" in sentence


def test_the_legacy_sentence_names_the_calls_and_the_source_of_the_claim():
    assessment = gap.assess(
        "langchain", ["1.4.2"], None, [], None, unpinned=True,
        legacy=[{"package": "langchain", "uses": "RetrievalQA", "note": "removed in langchain 1.x"}],
    )

    sentence = gap.legacy_sentence(assessment)

    assert "RetrievalQA" in sentence and "pattern table" in sentence


def test_there_is_no_legacy_sentence_without_markers():
    assessment = gap.assess("langchain", ["1.4.2"], "1.4.0", [], None)

    assert gap.legacy_sentence(assessment) == ""


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


def test_one_legacy_call_carries_its_own_note():
    assessment = gap.assess("langchain", ["1.4.2"], None, [], None, unpinned=True,
                            legacy=[{"package": "langchain", "uses": "RetrievalQA",
                                     "note": "removed in langchain 1.x"}])

    assert gap.legacy_sentence(assessment).endswith("says removed in langchain 1.x.")


def test_several_legacy_calls_are_listed_without_repeating_a_note():
    markers = [{"package": "langchain", "uses": name, "note": "removed in langchain 1.x"}
               for name in ("LLMChain", "RetrievalQA", "load_qa_chain")]
    assessment = gap.assess("langchain", ["1.4.2"], None, [], None, unpinned=True, legacy=markers)

    sentence = gap.legacy_sentence(assessment)

    assert "LLMChain, RetrievalQA and load_qa_chain" in sentence


def test_a_package_no_chapter_covers_is_described_as_a_gap():
    sentence = gap.describe("crewai", None, "1.15.22", gap.UNKNOWN, has_chapter=False)

    assert sentence.startswith("No chapter in the course installs or teaches crewai")
    assert "1.15.22" in sentence


def test_an_unbound_package_the_chapter_teaches_is_worth_rewriting():
    assessment = gap.assess("langchain", ["1.4.2"], None, [], None, unpinned=True, taught=True)

    assert assessment["kind"] == gap.UNPINNED
    assert assessment["kind"] in gap.ACTIONABLE


def test_an_unbound_dependency_the_chapter_never_teaches_is_not():
    assessment = gap.assess("pandas", ["3.0.6"], None, [], None, unpinned=True, taught=False)

    assert assessment["kind"] == gap.DEPENDENCY
    assert assessment["kind"] not in gap.ACTIONABLE
    assert "dependency to pin" in assessment["sentence"]


def test_a_removed_api_makes_even_an_untaught_package_actionable():
    markers = [{"package": "openai", "uses": "openai.ChatCompletion", "note": "removed in openai 1.x"}]
    assessment = gap.assess("openai", ["3.16.2"], None, [], None, unpinned=True,
                            taught=False, legacy=markers)

    assert assessment["kind"] == gap.UNPINNED
