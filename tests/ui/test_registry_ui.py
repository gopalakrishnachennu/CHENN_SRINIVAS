from resume_engine.ui.services import audit_service
from tests.ui._helpers import csrf_from, make_client


def test_registry_edit_audited(monkeypatch):
    client = make_client(monkeypatch)
    page = client.get("/registry/")
    token = csrf_from(page.data.decode())
    client.post("/registry/", data={"csrf_token":token, "action":"add_alias", "canonical":"AWS", "alias":"Amazon Web Services UITest"})
    events = audit_service.list_audit_events(action="registry.add_alias", limit=20)
    assert any(e.get("action") == "registry.add_alias" for e in events)
