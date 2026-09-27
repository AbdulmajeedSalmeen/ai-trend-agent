import pytest

from src.pin import set_pin


def curriculum():
    return {"chapters": [
        {"chapter_id": "C8", "pins": {"langchain": None}},
        {"chapter_id": "C19", "pins": {}},
    ]}


def test_recording_a_version_replaces_the_empty_pin():
    data = curriculum()

    set_pin(data, "C8", "langchain", "0.1.16")

    assert data["chapters"][0]["pins"] == {"langchain": "0.1.16"}


def test_a_chapter_can_pin_a_package_it_did_not_list():
    data = curriculum()

    set_pin(data, "C19", "langgraph", "0.2.34")

    assert data["chapters"][1]["pins"] == {"langgraph": "0.2.34"}


def test_clearing_removes_the_package():
    data = curriculum()
    set_pin(data, "C8", "langchain", "0.1.16")

    set_pin(data, "C8", "langchain", None)

    assert data["chapters"][0]["pins"] == {}


def test_an_unknown_chapter_is_refused():
    with pytest.raises(SystemExit):
        set_pin(curriculum(), "C99", "langchain", "1.0.0")
