import re

# Matches 1.2, 1.2.3, and pre-releases such as 0.0.1a2 or 2.0.0rc1.
# The pre-release part must be captured too: truncating "0.0.1a2" to "0.0"
# would let an alpha release confirm a claim about a different version.
VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)*(?:[a-z]+\d*)?)\b", re.IGNORECASE)


def extract_version(text: str) -> str | None:
    match = VERSION_RE.search(text)

    if match is None:
        return None

    return match.group(1)
