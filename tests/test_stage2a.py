import json
from pathlib import Path
from types import SimpleNamespace
from src.stages.stage2a_cluster import extract_version, signal_text


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