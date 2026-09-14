import json
from pathlib import Path


def test_curriculum_fixture_is_valid_json():
    data = json.loads(Path("fixtures/curriculum.json").read_text(encoding="utf-8"))
    assert data
