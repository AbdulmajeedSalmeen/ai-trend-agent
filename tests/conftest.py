import pytest


@pytest.fixture(autouse=True)
def model_off(monkeypatch):
    """No test may call a model. Stages fall back to their deterministic path."""
    monkeypatch.setattr("src.adapters.model.config", lambda: None)
