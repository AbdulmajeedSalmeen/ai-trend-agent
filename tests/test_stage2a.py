import json
from pathlib import Path

from src.stages.stage2a_cluster import extract_version


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