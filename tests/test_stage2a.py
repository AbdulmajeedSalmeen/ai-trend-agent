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

    assert len(claims) == 1
    assert claims[0].subject == "langgraph"
    assert claims[0].version == "2.0.0"
    assert claims[0].verdict == "unverified"
    assert claims[0].evidence_url is None
    assert claims[0].confidence == 0.2


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