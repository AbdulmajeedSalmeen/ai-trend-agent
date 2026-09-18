from datetime import datetime, timezone

from src.schema import Claim, Signal

from src.stages.stage2b_verify import find_evidence, verify_claim

def make_signal(subject, tier, title, url="https://example.com/x"):
    return Signal(
        id=f"s_{subject}_{tier}",
        source="github" if tier == 1 else "hackernews",
        tier=tier,
        subject=subject,
        title=title,
        url=url,
        published_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )


def test_exact_version_from_tier1_confirms():
    claim = Claim(
        text="LangGraph 0.6.0 was released",
        subject="langgraph",
        version="0.6.0",
    )

    signal = make_signal(
        subject="langgraph",
        tier=1,
        title="LangGraph 0.6.0 released",
    )

    evidence = find_evidence(claim, [signal])

    assert evidence is not None
    assert evidence == signal
    
def test_forum_post_never_confirms():
    claim = Claim(
        text="LangGraph 0.6.0 was released",
        subject="langgraph",
        version="0.6.0",
    )

    signal = make_signal(
        subject="langgraph",
        tier=2,
        title="LangGraph 0.6.0 released",
    )

    evidence = find_evidence(claim, [signal])

    assert evidence is None
    
def test_version_mismatch_stays_unverified():
    claim = Claim(
        text="LangGraph 5.6 was released",
        subject="langgraph",
        version="5.6",
    )

    signal = make_signal(
        subject="langgraph",
        tier=1,
        title="LangGraph 5.6.1 released",
    )

    evidence = find_evidence(claim, [signal])

    assert evidence is None
    
def test_versionless_claim_never_confirmed():
    claim = Claim(
        text="LangGraph was released",
        subject="langgraph",
        version=None,
    )

    signal = make_signal(
        subject="langgraph",
        tier=1,
        title="LangGraph 0.6.0 released",
    )

    evidence = find_evidence(claim, [signal])

    assert evidence is None
    
def test_wrong_subject_never_confirms():
    claim = Claim(
        text="LangGraph 0.6.0 was released",
        subject="langgraph",
        version="0.6.0",
    )

    signal = make_signal(
        subject="transformers",
        tier=1,
        title="Transformers 0.6.0 released",
    )

    evidence = find_evidence(claim, [signal])

    assert evidence is None
    
def test_confirmed_carries_evidence_url():
    claim = Claim(
        text="LangGraph 0.6.0 was released",
        subject="langgraph",
        version="0.6.0",
    )

    signal = make_signal(
        subject="langgraph",
        tier=1,
        title="LangGraph 0.6.0 released",
        url="https://github.com/langchain-ai/langgraph/releases/tag/0.6.0",
    )

    result = verify_claim(claim, [signal])

    assert result.verdict == "confirmed"
    assert result.evidence_url == signal.url
    assert result.confidence == 0.9

def test_same_version_different_subject_never_confirms():
    claim = Claim(
        text="langchain-anthropic 1.5.4 was released",
        subject="langchain-anthropic",
        version="1.5.4",
    )

    signal = make_signal(
        subject="langchain-core",
        tier=1,
        title="langchain-core 1.5.4 released",
    )

    evidence = find_evidence(claim, [signal])

    assert evidence is None

def make_claim(**overrides):
    data = dict(text="langgraph version 1.2.11 was released", subject="langgraph", version="1.2.11")
    data.update(overrides)
    return Claim(**data)


def test_claim_read_from_a_release_is_a_primary_report():
    release = make_signal("langgraph", 1, "langgraph 1.2.11")
    claim = make_claim(source_signal_id=release.id)

    verified = verify_claim(claim, [release])

    assert verified.verdict == "confirmed"
    assert verified.evidence_kind == "primary_report"
    assert verified.confidence == 0.7


def test_claim_read_elsewhere_and_backed_by_a_release_is_cross_source():
    release = make_signal("langgraph", 1, "langgraph 1.2.11")
    claim = make_claim(source_signal_id="hn_999")

    verified = verify_claim(claim, [release])

    assert verified.verdict == "confirmed"
    assert verified.evidence_kind == "cross_source"
    assert verified.confidence == 0.9


def test_evidence_from_another_document_wins_over_the_claims_own_document():
    own = make_signal("langgraph", 1, "langgraph 1.2.11", url="https://example.com/own")
    other = make_signal("langgraph", 1, "langgraph 1.2.11", url="https://example.com/other")
    other = other.model_copy(update={"id": "gh_other"})
    claim = make_claim(source_signal_id=own.id)

    verified = verify_claim(claim, [own, other])

    assert verified.evidence_kind == "cross_source"
    assert verified.evidence_url == "https://example.com/other"


def test_unverified_claim_carries_no_evidence_kind():
    claim = make_claim(version=None, source_signal_id="hn_1")

    verified = verify_claim(claim, [])

    assert verified.verdict == "unverified"
    assert verified.evidence_kind is None
