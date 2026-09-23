import pytest

from resume_engine.ui.services import learning_service
from tests.ui._helpers import make_client


def test_learning_dashboard_loads(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/learning/")
    assert r.status_code == 200
    assert b"SHADOW" in r.data
    assert b"ACTIVE MODE LOCKED" in r.data

def test_active_mode_cannot_be_enabled(monkeypatch):
    with pytest.raises(PermissionError):
        learning_service.try_enable_active_mode()

def test_replay_dry_run_through_service(monkeypatch):
    report = learning_service.replay_dry(actor="test")
    assert "dry_run" in report
    assert report.get("dry_run") is True
