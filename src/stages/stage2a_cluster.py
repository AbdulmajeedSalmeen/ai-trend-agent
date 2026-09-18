import re

from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from src.schema import Claim, Signal
from src.versions import extract_version 

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

    if not unknown:
        return known_groups

    if len(unknown) == 1:
        unknown_groups = [[unknown[0]]]
    else:
        texts = [signal_text(signal) for signal in unknown]

        vectors = TfidfVectorizer().fit_transform(texts)

        labels = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=distance_threshold,
            metric="cosine",
            linkage="average",
        ).fit_predict(vectors.toarray())

        clusters: dict[int, list[Signal]] = {}

        for label, signal in zip(labels, unknown):
            clusters.setdefault(int(label), []).append(signal)

        unknown_groups = list(clusters.values())

    remaining_unknown_groups: list[list[Signal]] = []

    for unknown_group in unknown_groups:
        attached = False

        for known_group in known_groups:
            subject = known_group[0].subject

            if subject is None:
                continue

            subject_words = subject.lower().replace("-", " ").replace("_", " ").split()

            group_titles = " ".join(
                signal.title.lower()
                for signal in unknown_group
            )

            if all(word in group_titles for word in subject_words):
                known_group.extend(unknown_group)
                attached = True
                break

        if not attached:
            remaining_unknown_groups.append(unknown_group)

    return known_groups + remaining_unknown_groups


def infer_subject(
    group: list[Signal],
    all_signals: list[Signal],
) -> str | None:
    direct_subject = next(
        (signal.subject for signal in group if signal.subject),
        None,
    )

    if direct_subject is not None:
        return direct_subject

    known_subjects = {
        signal.subject
        for signal in all_signals
        if signal.tier == 1 and signal.subject is not None
    }

    group_titles = " ".join(signal.title for signal in group)

    for subject in known_subjects:
        pattern = rf"\b{re.escape(subject)}\b"

        if re.search(pattern, group_titles, flags=re.IGNORECASE):
            return subject

    return None

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
        claim_text = group[0].title
    else:
        claim_text = f"{subject} version {version} was released"

    claim = Claim(
        text=claim_text,
        subject=subject,
        version=version,
        verdict="unverified",
        evidence_url=None,
        confidence=0.2,
    )

    return [claim]