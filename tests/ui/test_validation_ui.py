import pytest

from resume_engine.ui.paths import InvalidResumePath, resolve_validated_resume_path
from tests.ui._helpers import make_client


def test_validation_page_loads(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/validation/")
    assert r.status_code == 200

def test_rejected_artifact_cannot_masquerade_as_validated(monkeypatch):
    with pytest.raises(InvalidResumePath):
        resolve_validated_resume_path("resume_engine/storage/runs/x/y/rejected/V01.json")
