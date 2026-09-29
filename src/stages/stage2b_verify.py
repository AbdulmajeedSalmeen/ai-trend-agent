import os
from pathlib import Path

from src import runio
from src.adapters import model
from src.agents import extractor, verifier
from src.schema import Claim, Signal, Trend
from src.versions import extract_version

# How many claims a run may send the verifier after. Each one is a few pages fetched
# and a few model calls, and the claims it helps are the ones no second document
# happened to be collected for, which is most of them, so this is a sample not a sweep.
VERIFY_BUDGET = 8

# A version nobody wrote down was worked out by reading, so it is weaker than one the
# post stated. Every kind of check drops by this much when the version was extracted.
EXTRACTED_PENALTY = 0.15


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


def classify(claim: Claim, evidence: Signal, source_tier: int | None) -> tuple[str, float]:
    """What kind of check is this, and how much does it buy?

    The release repeating itself is the weakest. Two registries carrying the same
    version is stronger, but both are the publisher speaking, so it is not an
    independent check. Only a claim made somewhere else and then confirmed by an
    official release counts as cross-source.

    A version an agent worked out, rather than one the post wrote down, buys less of
    whichever of those it is: the check is the same, the thing being checked is an
    inference.
    """
    if evidence.id == claim.source_signal_id:
        kind, confidence = "primary_report", 0.7

    elif source_tier == 1:
        kind, confidence = "registry_match", 0.8

    else:
        kind, confidence = "cross_source", 0.9

    if claim.version_source == "extracted":
        confidence -= EXTRACTED_PENALTY

    return kind, round(confidence, 2)


def fill_version(claim: Claim, signals: list[Signal], extract) -> Claim:
    """Ask the extractor which release this post meant, and take it only if it stands.

    The agent answers with a version or with nothing, and nothing is the usual answer.
    What comes back has already been checked against the releases this run collected,
    so all that is left is to say on the claim that it was worked out, not stated.
    """
    post = next((signal for signal in signals if signal.id == claim.source_signal_id), None)

    if post is None:
        return claim

    found = extract(claim, post, signals)

    if not found:
        return claim

    return claim.model_copy(update={"version": found["version"], "version_source": "extracted"})


def verify_claim(claim: Claim, signals: list[Signal], tiers: dict[str, int] | None = None,
                 extract=None, second=None) -> Claim:
    if claim.version is None and extract is not None:
        claim = fill_version(claim, signals, extract)

    if claim.version is not None and claim.version_source is None:
        claim = claim.model_copy(update={"version_source": "stated"})

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

    source_tier = (tiers or {}).get(claim.source_signal_id or "")
    evidence_kind, confidence = classify(claim, evidence, source_tier)
    evidence_url, found_by = evidence.url, "collected"

    if evidence_kind == "primary_report" and second is not None:
        # The release page repeating itself is the weakest thing we call confirmed.
        # Ask where a second record of this version would be, and go and read it.
        found = second(claim, evidence.source)

        if found:
            evidence_kind, evidence_url, found_by = "registry_match", found["url"], "searched"
            confidence = 0.8 - (EXTRACTED_PENALTY if claim.version_source == "extracted" else 0)

    return claim.model_copy(
        update={
            "verdict": "confirmed",
            "evidence_url": evidence_url,
            "confidence": round(confidence, 2),
            "evidence_kind": evidence_kind,
            "evidence_found_by": found_by,
        }
    )


def searcher(budget: int | None = None, tools: dict | None = None, confirm=None):
    """Ask for a second source, until the budget for asking is spent.

    Every call is pages fetched and a model reading them, so a run samples rather than
    sweeps: it is worth knowing that the second record can be found at all, and worth
    more than spending a whole run's time proving it for every release in a month.
    """
    left = VERIFY_BUDGET if budget is None else budget
    confirm = confirm or verifier.confirm
    kit = tools if tools is not None else verifier.tools_for()

    def second(claim: Claim, came_from: str):
        nonlocal left

        if left <= 0:
            return None

        left -= 1
        return confirm(claim, came_from, tools=kit)

    return second


def run(run_dir: Path) -> None:
    signals = runio.load_artifact(run_dir, "signals", Signal)
    trends = runio.load_artifact(run_dir, "trends", Trend)

    tiers = {signal.id: signal.tier for signal in signals}
    verified_trends = []
    counts = {"cross_source": 0, "registry_match": 0, "primary_report": 0, "unverified": 0}
    extract = extractor.extract if model.available() else None
    second = searcher(int(os.environ.get("VERIFY_BUDGET", VERIFY_BUDGET))) if model.available() else None
    extracted = searched = 0

    if extract is not None:
        blank = sum(1 for trend in trends for claim in trend.claims if claim.version is None)
        print(f"think: {blank} claims state no version; asking which release each post meant")

    for trend in trends:
        verified_claims = []

        for claim in trend.claims:
            verified = verify_claim(claim, signals, tiers, extract=extract, second=second)
            counts[verified.evidence_kind or "unverified"] += 1
            extracted += verified.version_source == "extracted"
            searched += verified.evidence_found_by == "searched"
            verified_claims.append(verified)

        verified_trends.append(trend.model_copy(update={"claims": verified_claims}))

    print(
        f"verified: {counts['cross_source']} cross-source, "
        f"{counts['registry_match']} registry match, "
        f"{counts['primary_report']} primary report, "
        f"{counts['unverified']} unverified"
    )

    if extracted:
        print(f"{extracted} of those had no version until an agent worked out which release the post meant")

    if searched:
        print(f"{searched} rose from one document to two because an agent found where the second record was")

    runio.save_artifact(run_dir, "trends", verified_trends)
