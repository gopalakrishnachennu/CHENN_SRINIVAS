from tests.ui._helpers import make_client


def test_dashboard_loads(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b"Dashboard" in r.data
    assert b"River" in r.data
