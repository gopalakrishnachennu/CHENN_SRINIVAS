from resume_engine.ui.services import audit_service
from tests.ui._helpers import make_client


def test_audit_page_and_no_password_logged(monkeypatch):
    audit_service.record_audit_event(action="login", actor="operator", metadata={"password":"secret","api_key":"sk-abc"})
    events = audit_service.list_audit_events(action="login", limit=5)
    assert events
    meta = events[0].get("metadata_json") or ""
    assert "secret" not in meta
    assert "sk-abc" not in meta
    client = make_client(monkeypatch)
    r = client.get("/audit/")
    assert r.status_code == 200
