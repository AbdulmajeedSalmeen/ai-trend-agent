import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src import runio
from src.runio import load_artifact, new_run_id, run_dir, save_artifact
from src.schema import Signal


def make_signals(count):
    return [
        Signal(
            id=f"hn_{i}",
            source="hackernews",
            tier=2,
            title=f"story {i}",
            url=f"https://news.ycombinator.com/item?id={i}",
            published_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        )
        for i in range(count)
    ]


def test_run_id_format():
    run_id = new_run_id()

    assert run_id.startswith("run_")
    assert run_id.endswith("Z")
    assert ":" not in run_id


def test_run_dir_creates_run_and_raw_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(runio, "RUNS_DIR", tmp_path)

    path = run_dir("run_test")

    assert path.is_dir()
    assert (path / "raw").is_dir()


def test_run_dir_twice_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(runio, "RUNS_DIR", tmp_path)

    run_dir("run_test")
    run_dir("run_test")


def test_round_trip_keeps_every_item(tmp_path):
    signals = make_signals(3)

    save_artifact(tmp_path, "signals", signals)
    loaded = load_artifact(tmp_path, "signals", Signal)

    assert loaded == signals


def test_load_restores_datetime_type(tmp_path):
    save_artifact(tmp_path, "signals", make_signals(1))

    loaded = load_artifact(tmp_path, "signals", Signal)

    assert isinstance(loaded[0].published_at, datetime)


def test_load_rejects_file_that_breaks_the_contract(tmp_path):
    save_artifact(tmp_path, "signals", make_signals(1))
    path = tmp_path / "signals.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["source"] = "GitHub"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_artifact(tmp_path, "signals", Signal)