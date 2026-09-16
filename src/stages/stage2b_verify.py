from src.schema import Claim, Signal


def find_evidence(claim: Claim, signals: list[Signal]) -> Signal | None:
    if claim.version is None:
        return None

    for signal in signals:
        if signal.tier != 1:
            continue

        if signal.subject != claim.subject:
            continue

        if claim.version not in signal.title:
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