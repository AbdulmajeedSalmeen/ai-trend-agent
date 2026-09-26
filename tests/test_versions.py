from src.versions import extract_version


def test_patch_release_extracted_in_full():
    assert extract_version("v1.5.2") == "1.5.2"


def test_two_digit_major_extracted_in_full():
    assert extract_version("v11.5.0") == "11.5.0"


def test_extracted_version_does_not_equal_shorter_claim():
    assert extract_version("v11.5.0") != "1.5"

def test_prerelease_version_is_kept_whole():
    assert extract_version("langchain-typesafe==0.0.1a2") == "0.0.1a2"


def test_release_candidate_is_kept_whole():
    assert extract_version("v2.0.0rc1") == "2.0.0rc1"
