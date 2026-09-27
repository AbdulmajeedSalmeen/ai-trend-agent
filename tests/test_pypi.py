from datetime import datetime, timedelta, timezone

import pytest

from src.sources import pypi


def payload(**versions):
    return {
        "info": {"version": "1.4.2"},
        "releases": {
            version: [{"upload_time_iso_8601": stamp}] for version, stamp in versions.items()
        },
    }


def test_the_upload_time_is_the_first_file_to_land():
    files = [
        {"upload_time_iso_8601": "2026-09-18T17:31:10.056247Z"},
        {"upload_time_iso_8601": "2026-09-18T17:29:02.000000Z"},
    ]

    assert pypi.parse_upload_time(files).isoformat() == "2026-09-18T17:29:02+00:00"


def test_a_version_with_no_files_has_no_upload_time():
    assert pypi.parse_upload_time([]) is None


def test_an_unreadable_timestamp_is_skipped_not_guessed():
    files = [{"upload_time_iso_8601": "not a date"}, {"upload_time_iso_8601": "2026-09-01T00:00:00Z"}]

    assert pypi.parse_upload_time(files).year == 2026


def test_a_naive_timestamp_is_read_as_utc():
    assert pypi.parse_upload_time([{"upload_time": "2026-09-01T00:00:00"}]).tzinfo is not None


def test_trimming_drops_everything_outside_the_window():
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    data = payload(**{"1.4.2": "2026-09-18T00:00:00Z", "0.1.0": "2024-01-05T00:00:00Z"})

    trimmed = pypi.trim("langchain", data, since)

    assert list(trimmed["released"]) == ["1.4.2"]
    assert trimmed["latest"] == "1.4.2"
    assert trimmed["package"] == "langchain"


def test_trimming_survives_a_document_with_no_releases():
    assert pypi.trim("ghost", {"info": {}}, datetime(2026, 1, 1, tzinfo=timezone.utc))["released"] == {}


def test_a_release_becomes_a_tier_one_signal():
    signal = pypi.parse_release("langchain", "1.4.2", "2026-09-18T17:29:02+00:00")

    assert signal.tier == 1
    assert signal.source == "pypi"
    assert signal.subject == "langchain"
    assert signal.id == "pypi_langchain_1.4.2"
    assert signal.url == "https://pypi.org/project/langchain/1.4.2/"


def test_the_title_carries_the_version_so_the_extractor_reads_it():
    from src.versions import extract_version

    signal = pypi.parse_release("langchain-core", "1.6.3", "2026-09-18T00:00:00+00:00")

    assert extract_version(signal.title) == "1.6.3"


def test_one_package_failing_does_not_lose_the_others(monkeypatch):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")

    def fake_fetch(package, window, timeout=30):
        if package == "broken":
            return {"package": package, "error": "http 404"}
        return pypi.trim(package, payload(**{"1.4.2": recent}), window)

    monkeypatch.setattr(pypi, "fetch_one", fake_fetch)

    raw, signals = pypi.fetch_pypi(["langchain", "broken", "ragas"], days=30)

    assert len(raw) == 3
    assert sorted(s.subject for s in signals) == ["langchain", "ragas"]
    assert since < signals[0].published_at


def test_a_bad_status_is_reported_rather_than_raised(monkeypatch):
    class Response:
        status_code = 503

        def json(self):
            raise AssertionError("a failed response must never be parsed")

    monkeypatch.setattr(pypi.requests, "get", lambda *args, **kwargs: Response())

    assert pypi.fetch_one("langchain", datetime.now(timezone.utc)) == {
        "package": "langchain", "error": "http 503"
    }


def test_a_network_failure_is_reported_rather_than_raised(monkeypatch):
    def explode(*args, **kwargs):
        raise pypi.requests.Timeout("too slow")

    monkeypatch.setattr(pypi.requests, "get", explode)

    assert pypi.fetch_one("langchain", datetime.now(timezone.utc))["error"] == "Timeout"


def test_the_watchlist_comes_from_the_curriculum(tmp_path):
    import json

    path = tmp_path / "curriculum.json"
    path.write_text(json.dumps({"chapters": [
        {"chapter_id": "C8", "pins": {"langchain": "0.0.352"}, "installs_unpinned": ["pypdf"]},
        {"chapter_id": "C19", "pins": {}, "installs_unpinned": ["langgraph", "pypdf"]},
    ]}), encoding="utf-8")

    from src.curriculum import tracked_packages

    assert tracked_packages(path) == ["langchain", "langgraph", "pypdf"]


@pytest.mark.parametrize("field", ["package", "latest", "released"])
def test_the_trimmed_record_keeps_only_the_three_fields_we_read(field):
    trimmed = pypi.trim("ragas", payload(**{"0.4.3": "2026-09-18T00:00:00Z"}),
                        datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert field in trimmed
    assert set(trimmed) == {"package", "latest", "released"}
