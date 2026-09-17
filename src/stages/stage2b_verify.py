import re
from pathlib import Path

from src import runio
from src.schema import Claim, Signal, Trend

VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")

def find_evidence(claim: Claim, signals: list[Signal]) -> Signal | None:
    if claim.version is None:
        return None

    for signal in signals:
        if signal.tier != 1:
            continue

        if signal.subject != claim.subject:
            continue

        version_match = VERSION_RE.search(signal.title)

        if version_match is None:
            continue

        signal_version = version_match.group(1)

        if signal_version != claim.version:
            continue

        return signal

    return None

def verify_claim(claim: Claim, signals: list[Signal]) -> Claim:
    evidence = find_evidence(claim, signals)

    if evidence is not None:
        return claim.model_copy(
            update={
                "verdict": "confirmed",
                "evidence_url": evidence.url,
                "confidence": 0.9,
            }
        )

    return claim.model_copy(
        update={
            "verdict": "unverified",
            "evidence_url": None,
            "confidence": 0.2,
        }
    )

def run(run_dir: Path) -> None:
    signals = runio.load_artifact(run_dir, "signals", Signal)
    trends = runio.load_artifact(run_dir, "trends", Trend)

    verified_trends = []

    for trend in trends:
        verified_claims = []

        for claim in trend.claims:
            verified_claims.append(verify_claim(claim, signals))

        verified_trend = trend.model_copy(
            update={"claims": verified_claims}
        )
        verified_trends.append(verified_trend)

    runio.save_artifact(run_dir, "trends", verified_trends)