from src import changes

LANGGRAPH = """Changes since 1.2.10

* release(langgraph): 1.2.11 (#8595)
* feat(langgraph): expose `trace_policy` on `add_node` (#8523)
* chore(deps): bump the minor-and-patch group across 1 directory with 7 updates (#8533)
* chore(deps): bump the minor-and-patch group across 1 directory with 5 updates (#8532)
* fix(checkpoint): collect writes at plain-value seed in delta channel history (#8526)
* chore: enforce PLC0415 in tests for the remaining packages (#8547)
* test(checkpoint-postgres,checkpoint-sqlite): run the conformance suite (#8537)
"""

LANGCHAIN = """Changes since langchain==1.4.1

release(langchain): 1.4.2 (#40621)
fix(langchain): preserve model-generated tool calls in HITL tool call edits (#40463)
"""

ANTHROPIC = """## 1.7.0 (2026-09-18)

### Features

* **api:** add group with display_name to rate limits, deprecate group ([#640](https://github.com/x/y/issues/640))
* **tools:** add compact_before_next_turn() to the tool runner ([#641](https://github.com/x/y/issues/641))

### Bug Fixes

* **bedrock:** raise an API error for eventstream exception ([#642](https://github.com/x/y/issues/642))

### Chores

* **internal:** codegen related update
"""

PYDANTIC_AI = """<!-- Release notes generated using configuration in .github/release.yml at main -->

## What's Changed
### 🚀 Features
* Let `TypeSafeModel` fill a tool's arguments by @DouweM in https://github.com/pydantic/pydantic-ai/pull/8501
* Add `RealtimeSession.wait_for_playback()` by @DouweM in https://github.com/pydantic/pydantic-ai/pull/8141
### 🐛 Bug Fixes
* Handle empty tool outputs by @someone in https://github.com/pydantic/pydantic-ai/pull/8510
"""

CREWAI = """## What's Changed

### Features
- Support aliases as connection identifiers
- Add OpenRouter as a supported embedding provider

### Bug Fixes
- Accept CRLF in inline skill definitions
"""

BREAKING = """### ⚠ BREAKING CHANGES

* **client:** remove the deprecated `Completion` class

### Features

* add streaming helpers
"""


def test_a_chore_heavy_release_is_mostly_noise():
    summary = changes.classify(LANGGRAPH)

    assert summary["noise"] == 5
    assert summary["feature"] == 1
    assert summary["fix"] == 1


def test_the_feature_survives_and_the_chores_do_not():
    summary = changes.classify(LANGGRAPH)

    assert summary["highlights"] == ["feature: expose `trace_policy` on `add_node`"]


def test_a_release_line_without_a_bullet_is_still_read():
    summary = changes.classify(LANGCHAIN)

    assert summary["fix"] == 1
    assert summary["noise"] == 1
    assert summary["highlights"] == []


def test_release_please_sections_are_read_by_heading():
    summary = changes.classify(ANTHROPIC)

    assert summary["deprecation"] == 1
    assert summary["feature"] == 1
    assert summary["fix"] == 1
    assert summary["noise"] == 1


def test_a_feature_that_deprecates_something_is_a_deprecation():
    summary = changes.classify(ANTHROPIC)

    assert summary["highlights"][0].startswith("deprecation: api: add group with display_name")


def test_an_emoji_heading_is_read_by_its_word():
    summary = changes.classify(PYDANTIC_AI)

    assert summary["feature"] == 2
    assert summary["fix"] == 1


def test_the_author_and_link_are_cleaned_off():
    summary = changes.classify(PYDANTIC_AI)

    assert "by @DouweM" not in " ".join(summary["highlights"])
    assert "https://" not in " ".join(summary["highlights"])


def test_plain_sections_with_dashes_are_read():
    summary = changes.classify(CREWAI)

    assert summary["feature"] == 2
    assert summary["fix"] == 1


def test_a_breaking_section_outranks_everything():
    summary = changes.classify(BREAKING)

    assert summary["breaking"] == 1
    assert summary["highlights"][0].startswith("breaking: client: remove the deprecated")


def test_an_exclamation_mark_on_a_commit_is_breaking():
    summary = changes.classify("feat(api)!: rename `invoke` to `run`")

    assert summary["breaking"] == 1


def test_a_feature_that_removes_support_is_breaking():
    summary = changes.classify("* feat: drop support for Python 3.9")

    assert summary["breaking"] == 1


def test_a_fix_that_removes_an_argument_stays_a_fix():
    summary = changes.classify("* fix: remove the stray argument that broke retries")

    assert summary["fix"] == 1
    assert summary["breaking"] == 0


def test_an_unknown_prefix_that_adds_something_is_a_feature():
    summary = changes.classify("vibevoice: add the VibeVoice speech model")

    assert summary["feature"] == 1


def test_empty_notes_change_nothing():
    summary = changes.classify("")

    assert all(summary[kind] == 0 for kind in changes.KINDS)
    assert summary["highlights"] == []


def test_combining_several_releases_adds_them_up_without_repeating_highlights():
    one = changes.classify(LANGGRAPH)
    total = changes.combine([one, one, changes.classify(CREWAI)])

    assert total["feature"] == 4
    assert total["highlights"].count("feature: expose `trace_policy` on `add_node`") == 1
    assert total["teachable"] == 4


def test_impact_follows_what_changed_not_how_often():
    chores_only = changes.combine([changes.classify("* chore: bump deps")] * 10)
    one_break = changes.combine([changes.classify(BREAKING)])

    assert changes.weight(chores_only) == 1
    assert changes.weight(one_break) == 5


def test_fixes_alone_are_worth_little():
    assert changes.weight(changes.combine([changes.classify(LANGCHAIN)])) == 2


def test_a_prerelease_is_recognised():
    assert changes.is_prerelease("1.4.0a4")
    assert changes.is_prerelease("3.4.0b1")
    assert changes.is_prerelease("1.103.0rc1")
    assert not changes.is_prerelease("1.4.2")


def test_emoji_shortcodes_and_commit_hashes_are_not_part_of_the_change():
    summary = changes.classify("### Breaking\n* :rotating_light: Vision rotary embeddings (2d4e9f1)")

    assert summary["highlights"] == ["breaking: Vision rotary embeddings"]


def test_a_leading_emoji_is_dropped():
    summary = changes.classify("### Breaking changes\n* 🚨 TP dtensor API inference")

    assert summary["highlights"] == ["breaking: TP dtensor API inference"]


def test_a_fix_for_a_breaking_change_is_a_fix_not_a_break():
    summary = changes.classify("### Bug Fixes\n* Fix Breaking Change in Message Block Buffer Resolution")

    assert summary["fix"] == 1
    assert summary["breaking"] == 0


def test_a_chore_that_announces_a_breaking_change_is_breaking():
    summary = changes.classify("### Chores\n* client: upgrade to httpx2 and some minor breaking changes")

    assert summary["breaking"] == 1


def test_an_unsorted_line_that_opens_with_fix_is_a_fix():
    summary = changes.classify("### llama-index-core [0.14.21]\n- Fix Breaking Change in Message Block Buffer Resolution")

    assert summary["fix"] == 1
    assert summary["breaking"] == 0


def test_a_change_listed_twice_in_one_release_counts_once():
    notes = ("### Chores\n* client: upgrade to httpx2 and some minor breaking changes\n"
             "### Refactors\n* client: upgrade to httpx2 and some minor breaking changes\n")

    assert changes.classify(notes)["breaking"] == 1
