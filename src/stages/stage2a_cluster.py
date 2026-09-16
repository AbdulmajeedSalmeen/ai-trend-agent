import re

from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_distances


from src.schema import Claim, Signal

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


def cluster_signals(
    signals: list[Signal],
    distance_threshold: float = 0.8,
) -> list[list[Signal]]:
    if not signals:
        return []

    if len(signals) == 1:
        return [signals]

    known_groups, unknown = group_known_subjects(signals)

    units: list[list[Signal]] = known_groups + [[signal] for signal in unknown]

    if len(units) == 1:
        return units

    texts = [
        " ".join(signal_text(signal) for signal in group)
        for group in units
    ]

    vectors = TfidfVectorizer().fit_transform(texts)
    distances = cosine_distances(vectors)

    model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="precomputed",
        linkage="average",
    )

    labels = model.fit_predict(distances)

    clusters: dict[int, list[Signal]] = {}

    for label, group in zip(labels, units):
        clusters.setdefault(int(label), []).extend(group)

    return list(clusters.values())



def make_claims(group: list[Signal]) -> list[Claim]:
    if not group:
        return []

    subject = next(
        (signal.subject for signal in group if signal.subject),
        None,
    )

    if subject is None:
        return []

    tier1_version = None

    for signal in group:
        if signal.tier == 1:
            tier1_version = extract_version(
                f"{signal.title} {signal.body}"
            )

            if tier1_version is not None:
                break

    version = tier1_version

    if version is None:
        for signal in group:
            version = extract_version(
                f"{signal.title} {signal.body}"
            )

            if version is not None:
                break

    if version is None:
        return []

    claim = Claim(
        text=f"{subject} version {version} was released",
        subject=subject,
        version=version,
        verdict="unverified",
        evidence_url=None,
        confidence=0.2,
    )

    return [claim]