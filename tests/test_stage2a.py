import json
from pathlib import Path
from src.schema import Signal
from types import SimpleNamespace
from src.stages.stage2a_cluster import (
    extract_version,
    signal_text,
    group_known_subjects,
    cluster_signals,
    make_claims,
    infer_subject,
    run,
)

def load_fixture_signals() -> list[Signal]:
    path = Path("fixtures/samples/signals_fixture.json")
    data = json.loads(path.read_text(encoding="utf-8"))

    return [Signal.model_validate(item) for item in data]


def test_extract_version_three_parts():
    assert extract_version("Release v2.0.0") == "2.0.0"


def test_extract_version_keeps_full_version():
    assert extract_version("GPT-5.6.1 launched") == "5.6.1"


def test_extract_version_returns_none_without_version():
    assert extract_version("no numbers here") is None


def test_extract_version_uses_first_version():
    assert extract_version("upgrade 5.6 to 5.6.1") == "5.6"


def test_signals_fixture_has_12_signals():
    path = Path("fixtures/samples/signals_fixture.json")
    signals = json.loads(path.read_text(encoding="utf-8"))

    assert len(signals) == 12


def test_signal_text_combines_subject_title_and_body():
    signal = SimpleNamespace(
        subject="langgraph",
        title="LangGraph 2.0 released",
        body="Durable execution improvements",
    )

    text = signal_text(signal)

    assert "langgraph" in text
    assert "LangGraph 2.0 released" in text
    assert "Durable execution improvements" in text


def test_signal_text_handles_empty_body():
    signal = SimpleNamespace(
        subject=None,
        title="New LangGraph release",
        body="",
    )

    text = signal_text(signal)

    assert "New LangGraph release" in text


def test_group_known_subjects_groups_same_subject():
    signals = [
        SimpleNamespace(subject="langgraph", id="gh_1"),
        SimpleNamespace(subject="langgraph", id="gh_2"),
        SimpleNamespace(subject="transformers", id="gh_3"),
    ]

    groups, unknown = group_known_subjects(signals)

    group_ids = [{signal.id for signal in group} for group in groups]

    assert {"gh_1", "gh_2"} in group_ids
    assert {"gh_3"} in group_ids
    assert unknown == []


def test_group_known_subjects_separates_unknown_subjects():
    signals = [
        SimpleNamespace(subject="langgraph", id="gh_1"),
        SimpleNamespace(subject=None, id="hn_1"),
        SimpleNamespace(subject=None, id="hn_2"),
    ]

    groups, unknown = group_known_subjects(signals)

    assert len(groups) == 1
    assert [signal.id for signal in unknown] == ["hn_1", "hn_2"]


def test_cluster_signals_empty():
    assert cluster_signals([]) == []


def test_cluster_signals_one_signal():
    signal = Signal(
        id="test_1",
        source="hackernews",
        tier=2,
        subject=None,
        title="LangGraph release",
        url="https://example.com/1",
        published_at="2026-09-16T08:00:00+00:00",
        body="",
    )

    groups = cluster_signals([signal])

    assert groups == [[signal]]



def test_cluster_signals_groups_all_langgraph_signals_together():
    signals = load_fixture_signals()

    groups = cluster_signals(signals)

    langgraph_ids = {
        signal.id
        for signal in signals
        if "langgraph" in signal_text(signal).lower()
    }

    matching_groups = [
        group
        for group in groups
        if langgraph_ids.issubset({signal.id for signal in group})
    ]

    assert len(langgraph_ids) == 4
    assert len(matching_groups) == 1



def test_cluster_signals_keeps_transformers_and_openai_separate():
    signals = load_fixture_signals()

    groups = cluster_signals(signals)

    transformers_ids = {
        signal.id
        for signal in signals
        if "transformers" in signal_text(signal).lower()
    }

    openai_ids = {
        signal.id
        for signal in signals
        if "openai" in signal_text(signal).lower()
    }

    assert len(transformers_ids) == 3
    assert len(openai_ids) == 2

    for group in groups:
        group_ids = {signal.id for signal in group}

        assert not (
            transformers_ids & group_ids
            and openai_ids & group_ids
        )

def test_cluster_signals_keeps_unrelated_signals_as_singletons():
    signals = load_fixture_signals()

    groups = cluster_signals(signals)

    unrelated_ids = {
        "hn_unrelated_001",
        "hn_unrelated_002",
        "hn_unrelated_003",
    }

    for unrelated_id in unrelated_ids:
        matching_groups = [
            group
            for group in groups
            if unrelated_id in {signal.id for signal in group}
        ]

        assert len(matching_groups) == 1
        assert len(matching_groups[0]) == 1


def test_make_claims_prefers_tier1_version():
    signals = load_fixture_signals()

    langgraph_group = [
        signal
        for signal in signals
        if "langgraph" in signal_text(signal).lower()
    ]

    claims = make_claims(langgraph_group)

    # The release claim comes first; a discussion claim may follow it.
    assert claims[0].subject == "langgraph"
    assert claims[0].version == "2.0.0"
    assert claims[0].verdict == "unverified"
    assert claims[0].evidence_url is None
    assert claims[0].confidence == 0.2
    assert claims[0].source_signal_id is not None


def test_make_claims_also_reports_what_the_discussion_says():
    signals = load_fixture_signals()

    langgraph_group = [
        signal
        for signal in signals
        if "langgraph" in signal_text(signal).lower()
    ]

    claims = make_claims(langgraph_group)
    discussion = [claim for claim in claims if claim.source_signal_id.startswith("hn_")]

    assert len(discussion) == 1
    assert discussion[0].verdict == "unverified"


def test_make_claims_removes_duplicate_subject_version():
    signals = load_fixture_signals()

    langgraph_group = [
        signal
        for signal in signals
        if "langgraph" in signal_text(signal).lower()
    ]

    claims = make_claims(langgraph_group)

    pairs = [
        (claim.subject, claim.version)
        for claim in claims
    ]

    assert len(pairs) == len(set(pairs))


def test_infer_subject_from_tier1_dictionary():
    signals = load_fixture_signals()

    group = [
        signal
        for signal in signals
        if signal.subject is None
        and "langgraph" in signal.title.lower()
    ]

    subject = infer_subject(group, signals)

    assert subject == "langgraph"


def test_infer_subject_returns_none_for_unrelated_group():
    signals = load_fixture_signals()

    group = [
        signal
        for signal in signals
        if signal.id == "hn_unrelated_001"
    ]

    subject = infer_subject(group, signals)

    assert subject is None



def test_make_claims_without_version_uses_title():
    signal = Signal(
        id="gh_langgraph_no_version",
        source="github",
        tier=1,
        subject="langgraph",
        title="LangGraph improves durable execution",
        url="https://example.com/langgraph",
        published_at="2026-09-18T08:00:00+00:00",
        body="No version number in this release note.",
    )

    claims = make_claims([signal])

    assert len(claims) == 1
    assert claims[0].subject == "langgraph"
    assert claims[0].version is None
    assert claims[0].text == "LangGraph improves durable execution"
    assert claims[0].verdict == "unverified"
    assert claims[0].evidence_url is None
    assert claims[0].confidence == 0.2



def test_make_claims_uses_subject_override_for_subjectless_group():
    signals = load_fixture_signals()

    group = [
        signal
        for signal in signals
        if signal.subject is None
        and "langgraph" in signal.title.lower()
    ]

    subject = infer_subject(group, signals)

    claims = make_claims(
        group,
        subject_override=subject,
    )

    assert subject == "langgraph"
    assert len(claims) == 1
    assert claims[0].subject == "langgraph"
    assert claims[0].version == "2.0"
    assert claims[0].verdict == "unverified"
    assert claims[0].evidence_url is None
    assert claims[0].confidence == 0.2


def test_run_writes_trends_and_skips_unknown_subjects(tmp_path, capsys):
    source = Path("fixtures/samples/signals_fixture.json")
    destination = tmp_path / "signals.json"
    destination.write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    run(tmp_path)

    trends_path = tmp_path / "trends.json"

    assert trends_path.exists()

    trends = json.loads(
        trends_path.read_text(encoding="utf-8")
    )

    assert len(trends) == 3

    subjects = {trend["subject"] for trend in trends}

    assert subjects == {
        "langgraph",
        "transformers",
        "openai-python",
    }

    assert [trend["id"] for trend in trends] == [
        "trend_001",
        "trend_002",
        "trend_003",
    ]

    output = capsys.readouterr().out

    assert "skipped 3 clusters with no identifiable subject" in output


def test_make_claims_returns_unique_tier1_versions_newest_first():
    signals = [
        Signal(
            id="gh_langgraph_1_2_9",
            source="github",
            tier=1,
            subject="langgraph",
            title="LangGraph 1.2.9 released",
            url="https://example.com/1.2.9",
            published_at="2026-09-16T08:00:00+00:00",
            body="",
        ),
        Signal(
            id="gh_langgraph_1_2_10",
            source="github",
            tier=1,
            subject="langgraph",
            title="LangGraph 1.2.10 released",
            url="https://example.com/1.2.10",
            published_at="2026-09-17T08:00:00+00:00",
            body="",
        ),
        Signal(
            id="gh_langgraph_1_2_9_duplicate",
            source="github",
            tier=1,
            subject="langgraph",
            title="LangGraph 1.2.9 released again",
            url="https://example.com/1.2.9-duplicate",
            published_at="2026-09-18T08:00:00+00:00",
            body="",
        ),
    ]


    claims = make_claims(signals)

    release_claims = [
        claim
        for claim in claims
        if claim.source_signal_id.startswith("gh_")
    ]

    assert [claim.version for claim in release_claims] == [
        "1.2.10",
        "1.2.9",
    ]


def test_make_claims_deduplicates_discussion_with_same_subject_version():
    signals = [
        Signal(
            id="gh_langgraph_1_2_10",
            source="github",
            tier=1,
            subject="langgraph",
            title="LangGraph 1.2.10 released",
            url="https://example.com/github",
            published_at="2026-09-18T08:00:00+00:00",
            body="",
        ),
        Signal(
            id="hn_langgraph_1_2_10",
            source="hackernews",
            tier=2,
            subject=None,
            title="LangGraph 1.2.10 discussion",
            url="https://example.com/hn",
            published_at="2026-09-18T09:00:00+00:00",
            body="",
        ),
    ]

    claims = make_claims(signals)

    pairs = [
        (claim.subject, claim.version)
        for claim in claims
    ]

    assert pairs.count(("langgraph", "1.2.10")) == 1

# A post that says something real and never writes the version down used to be thrown
# away here, which is most of them. The extractor gets one chance at it first, and when
# it cannot say, the reading is dropped exactly as it always was.

from datetime import datetime, timezone

from src.stages import stage2a_cluster
from src.schema import Trend


def _post(ident="hn_1"):
    return Signal(id=ident, source="hackernews", tier=2, subject=None,
                  title="The new langgraph release broke my agent",
                  url="https://news.ycombinator.com/item?id=1",
                  published_at=datetime(2026, 9, 22, tzinfo=timezone.utc), body="")


def _release():
    return Signal(id="gh_1", source="github", tier=1, subject="langgraph", title="langgraph==1.2.12",
                  url="https://github.com/x/releases/1.2.12",
                  published_at=datetime(2026, 9, 21, tzinfo=timezone.utc), body="notes")


def _trend():
    return Trend(id="trend_001", subject="langgraph", signal_ids=["hn_1", "gh_1"], claims=[])


def _never_asked(*args):
    raise AssertionError("the extractor was asked about a version the post already stated")


def _reading(version=None):
    return {"subject": "langgraph", "assertion": "the react agent constructor is gone", "version": version}


def test_a_version_the_post_stated_needs_no_agent(monkeypatch):
    monkeypatch.setattr(stage2a_cluster, "read_claim", lambda post, vocabulary: _reading("1.2.12"))
    trends = [_trend()]

    read, checkable, worked_out = stage2a_cluster.read_discussion_claims(
        trends, [_post(), _release()], budget=5, extract=_never_asked)

    assert (read, checkable, worked_out) == (1, 1, 0)
    assert trends[0].claims[0].version_source == "stated"


def test_a_version_the_agent_worked_out_becomes_a_claim_that_says_so(monkeypatch):
    monkeypatch.setattr(stage2a_cluster, "read_claim", lambda post, vocabulary: _reading(None))
    trends = [_trend()]

    read, checkable, worked_out = stage2a_cluster.read_discussion_claims(
        trends, [_post(), _release()], budget=5,
        extract=lambda claim, post, signals: {"version": "1.2.12"})

    assert (read, checkable, worked_out) == (1, 1, 1)
    claim = trends[0].claims[0]
    assert claim.version == "1.2.12" and claim.version_source == "extracted"
    assert claim.source_signal_id == "hn_1" and claim.confidence == 0.2


def test_a_reading_the_agent_cannot_place_is_dropped_the_way_it_always_was(monkeypatch):
    monkeypatch.setattr(stage2a_cluster, "read_claim", lambda post, vocabulary: _reading(None))
    trends = [_trend()]

    assert stage2a_cluster.read_discussion_claims(
        trends, [_post(), _release()], budget=5, extract=lambda *args: None) == (1, 0, 0)
    assert trends[0].claims == []

    # and with no extractor at all, nothing about this door changes
    assert stage2a_cluster.read_discussion_claims(trends, [_post(), _release()], budget=5) == (1, 0, 0)
    assert trends[0].claims == []


def test_a_post_about_another_package_is_never_extracted_for(monkeypatch):
    monkeypatch.setattr(stage2a_cluster, "read_claim",
                        lambda post, vocabulary: {**_reading(None), "subject": "transformers"})
    trends = [_trend()]
    asked = []

    assert stage2a_cluster.read_discussion_claims(
        trends, [_post(), _release()], budget=5,
        extract=lambda *args: asked.append(args)) == (1, 0, 0)
    assert asked == []


def test_the_budget_is_what_stops_it(monkeypatch):
    monkeypatch.setattr(stage2a_cluster, "read_claim", lambda post, vocabulary: _reading("1.2.12"))
    posts = [_post(f"hn_{n}") for n in range(3)]
    trends = [Trend(id="trend_001", subject="langgraph", signal_ids=[p.id for p in posts], claims=[])]

    read, checkable, _ = stage2a_cluster.read_discussion_claims(trends, posts + [_release()], budget=2)
    assert (read, checkable) == (2, 2)
