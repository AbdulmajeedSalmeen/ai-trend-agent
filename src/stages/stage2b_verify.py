from pathlib import Path

from src import runio
from src.schema import Claim, Signal, Trend
from src.versions import extract_version


def find_evidence(claim: Claim, signals: list[Signal]) -> Signal | None:
    """The official release that states exactly what the claim says, or None.

    A claim with no version states nothing checkable, so it is never confirmed.
    Evidence from a document other than the one the claim was read from is
    preferred: that is a real check rather than a document repeating itself.
    """
    if claim.version is None:
        return None

    candidates = [
        signal
        for signal in signals
        if signal.tier == 1
        and signal.subject == claim.subject
        and extract_version(signal.title) == claim.version
    ]

    for signal in candidates:
        if signal.id != claim.source_signal_id:
            return signal

    if candidates:
        return candidates[0]

    return None


def verify_claim(claim: Claim, signals: list[Signal]) -> Claim:
    evidence = find_evidence(claim, signals)

    if evidence is None:
        return claim.model_copy(
            update={
                "verdict": "unverified",
                "evidence_url": None,
                "confidence": 0.2,
                "evidence_kind": None,
            }
        )

    if evidence.id == claim.source_signal_id:
        evidence_kind = "primary_report"
        confidence = 0.7
    else:
        evidence_kind = "cross_source"
        confidence = 0.9

    return claim.model_copy(
        update={
            "verdict": "confirmed",
            "evidence_url": evidence.url,
            "confidence": confidence,
            "evidence_kind": evidence_kind,
        }
    )


def run(run_dir: Path) -> None:
    signals = runio.load_artifact(run_dir, "signals", Signal)
    trends = runio.load_artifact(run_dir, "trends", Trend)

    verified_trends = []
    counts = {"cross_source": 0, "primary_report": 0, "unverified": 0}

    for trend in trends:
        verified_claims = []

        for claim in trend.claims:
            verified = verify_claim(claim, signals)
            counts[verified.evidence_kind or "unverified"] += 1
            verified_claims.append(verified)

        verified_trends.append(trend.model_copy(update={"claims": verified_claims}))

    print(
        f"verified: {counts['cross_source']} cross-source, "
        f"{counts['primary_report']} primary report, "
        f"{counts['unverified']} unverified"
    )

    runio.save_artifact(run_dir, "trends", verified_trends)
