import os
import subprocess
import sys
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src import runio
from web import runner, server
from src.schema import Claim, Recommendation, Score, Signal, Trend


def seed_run(path):
    signal = Signal(
        id="gh_langgraph_1.2.11", source="github", tier=1, subject="langgraph",
        title="langgraph 1.2.11", url="https://example.com/r",
        published_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )
    claim = Claim(text="langgraph version 1.2.11 was released", subject="langgraph", version="1.2.11",
                  verdict="confirmed", evidence_url=signal.url, confidence=0.7,
                  source_signal_id=signal.id, evidence_kind="primary_report")
    trend = Trend(id="trend_001", subject="langgraph", signal_ids=[signal.id], claims=[claim])
    runio.save_artifact(path, "signals", [signal])
    runio.save_artifact(path, "trends", [trend])
    runio.save_artifact(path, "scores", [Score(trend_id="trend_001", chapter_id="C19", confidence=0.7,
                                               dimensions={"relevance": 5}, provenance={"relevance": "measured"},
                                               priority=3.4)])
    runio.save_artifact(path, "recommendations", [Recommendation(trend_id="trend_001",
                                                                 action="update_existing_material",
                                                                 chapter_id="C19", rationale="langgraph moved.")])


def test_index_serves_the_page_without_embedded_data():
    body = TestClient(server.app).get("/").text

    assert "AI Trend Agent" in body
    assert "__DATA__" not in body


def test_run_payload_reads_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(runio, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(runner.runio, "RUNS_DIR", tmp_path)
    run_dir = tmp_path / "run_20260919T000000Z"
    run_dir.mkdir()
    seed_run(run_dir)

    client = TestClient(server.app)
    listing = client.get("/api/runs").json()
    payload = client.get("/api/run/run_20260919T000000Z").json()

    assert listing["runs"][0]["complete"] is True
    assert payload["items"][0]["subject"] == "langgraph"


def test_unknown_run_is_404():
    assert TestClient(server.app).get("/api/run/run_does_not_exist").status_code == 404


def test_second_run_is_refused_while_one_is_running(monkeypatch):
    monkeypatch.setattr(runner, "_status", {**runner.status(), "state": "running"}, raising=False)

    result = runner.start(None)

    assert result["ok"] is False
    assert result["reason"] == "already_running"


def test_a_browser_run_gets_its_own_trace_and_resets_the_breaker(tmp_path, monkeypatch):
    from src import trace
    from src.adapters import model as model_adapter
    from web import runner as runner_module

    monkeypatch.setattr(runio, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(runner_module, "STAGES", [("verify", lambda run_path: print("verified: ok"))])

    model_adapter._halted["openai"] = "HTTP 429"

    runner_module._execute("run_20260920T090000Z", replay=True)

    assert model_adapter.halted() is None
    assert trace.current.run_id == "run_20260920T090000Z"
    assert (tmp_path / "run_20260920T090000Z" / "trace.json").exists()


def test_a_lock_left_by_a_stopped_server_is_taken_over(tmp_path, monkeypatch):
    lock = tmp_path / ".run.lock"
    lock.write_text("run_20260921T220316Z 2026-09-21T22:03:16+00:00 424242", encoding="utf-8")
    monkeypatch.setattr(runner, "LOCK_PATH", lock)
    monkeypatch.setattr(runner, "_alive", lambda pid: False)

    assert runner._acquire_lock("run_20260922T000000Z")

    run_id, _, pid = lock.read_text(encoding="utf-8").split()
    assert run_id == "run_20260922T000000Z"
    assert pid == str(os.getpid())


def test_a_lock_whose_server_is_still_running_is_respected(tmp_path, monkeypatch):
    lock = tmp_path / ".run.lock"
    lock.write_text(f"run_20260922T000000Z 2026-09-22T00:00:00+00:00 {os.getpid()}", encoding="utf-8")
    monkeypatch.setattr(runner, "LOCK_PATH", lock)

    assert not runner._acquire_lock("run_20260922T010000Z")
    assert lock.read_text(encoding="utf-8").startswith("run_20260922T000000Z")


def test_a_lock_that_names_no_owner_is_treated_as_abandoned(tmp_path, monkeypatch):
    lock = tmp_path / ".run.lock"
    lock.write_text("run_20260921T220316Z 2026-09-21T22:03:16+00:00", encoding="utf-8")
    monkeypatch.setattr(runner, "LOCK_PATH", lock)

    assert runner._acquire_lock("run_20260922T000000Z")


def test_a_finished_process_is_not_alive_and_this_one_is():
    with subprocess.Popen([sys.executable, "-c", "pass"]) as finished:
        finished.wait()

    assert runner._alive(os.getpid())
    assert not runner._alive(finished.pid)


def test_the_tab_icon_is_the_one_the_page_declares(tmp_path, monkeypatch):
    page = tmp_path / "template.html"
    page.write_text('<head><link rel="icon" type="image/svg+xml" href="data:image/svg+xml,'
                    "%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3C/svg%3E\"></head>", encoding="utf-8")
    monkeypatch.setattr(server.site, "TEMPLATE_PATH", page)

    response = TestClient(server.app).get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text == "<svg xmlns='http://www.w3.org/2000/svg'></svg>"


def test_a_page_without_an_icon_answers_the_tab_with_no_content(tmp_path, monkeypatch):
    bare = tmp_path / "template.html"
    bare.write_text("<html><head><title>x</title></head></html>", encoding="utf-8")
    monkeypatch.setattr(server.site, "TEMPLATE_PATH", bare)

    assert TestClient(server.app).get("/favicon.ico").status_code == 204
