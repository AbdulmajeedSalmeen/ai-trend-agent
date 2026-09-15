import re


VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")


def extract_version(text: str) -> str | None:
    match = VERSION_RE.search(text)

    if match is None:
        return None

    return match.group(1)