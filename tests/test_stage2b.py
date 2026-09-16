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
        text="LangGraph 0.6.0 was released",
        subject="langgraph",
        version="0.6.0",
    )

    signal = make_signal(
        subject="langgraph",
        tier=1,
        title="LangGraph 0.6.1 released",
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