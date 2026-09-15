import re


VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")


def extract_version(text: str) -> str | None:
    match = VERSION_RE.search(text)

    if match is None:
        return None

    return match.group(1)


def signal_text(s) -> str:
    return f"{s.subject or ''} {s.title} {s.body[:500]}"


def group_known_subjects(signals):
    groups = {}
    unknown = []

    for signal in signals:
        if signal.subject:
            groups.setdefault(signal.subject, []).append(signal)
        else:
            unknown.append(signal)

    return list(groups.values()), unknown