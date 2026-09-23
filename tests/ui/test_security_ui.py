from tests.ui._helpers import login, make_client


def test_auth_required_when_enabled(monkeypatch):
    client = make_client(monkeypatch, password="s3cret")
    r = client.get("/", follow_redirects=False)
    assert r.status_code in {302, 303}
    assert "/login" in (r.headers.get("Location") or "")

def test_health_remains_public(monkeypatch):
    client = make_client(monkeypatch, password="s3cret")
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

def test_csrf_blocks_invalid_mutation(monkeypatch):
    client = make_client(monkeypatch, password="s3cret")
    login(client)
    r = client.post("/settings/", data={"key":"default_variant_count","value":"3","csrf_token":"bad"}, follow_redirects=False)
    assert r.status_code == 400

def test_path_traversal_rejected(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/view", query_string={"path":"../../etc/passwd"})
    assert r.status_code == 404

def test_external_redirect_rejected(monkeypatch):
    from resume_engine.ui.app import create_app
    from resume_engine.ui.auth import safe_next_url
    app = create_app()
    with app.app_context():
        assert safe_next_url("https://evil.example") == "/"
        assert safe_next_url("//evil.example") == "/"

def test_api_key_never_appears_in_html(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-should-not-leak")
    client = make_client(monkeypatch)
    for path in ["/", "/settings/", "/system/"]:
        r = client.get(path)
        assert r.status_code == 200
        assert b"sk-test-secret-should-not-leak" not in r.data
        assert b"CONFIGURED" in r.data or b"NOT CONFIGURED" in r.data or b"System" in r.data or b"Dashboard" in r.data
