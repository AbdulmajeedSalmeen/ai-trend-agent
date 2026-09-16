import re
from src.schema import Signal

VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")


def extract_version(text: str) -> str | None:
    match = VERSION_RE.search(text)

    if match is None:
        return None

    return match.group(1)


def signal_text(s: Signal) -> str:
    return f"{s.subject or ''} {s.title} {s.body[:500]}"


def group_known_subjects(
    signals: list[Signal],
) -> tuple[list[list[Signal]], list[Signal]]:
    groups: dict[str, list[Signal]] = {}
    unknown: list[Signal] = []

    for signal in signals:
        if signal.subject:
            groups.setdefault(signal.subject, []).append(signal)
        else:
            unknown.append(signal)

    return list(groups.values()), unknown