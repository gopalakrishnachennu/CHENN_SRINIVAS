from tests.ui._helpers import make_client


def test_dashboard_loads(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b"Dashboard" in r.data
    assert b"Add Candidates" in r.data
    assert b"Create Resume" in r.data
    # Technical metrics stay off the simple dashboard
    assert b"River observations" not in r.data
    assert b"P1 coverage" not in r.data
