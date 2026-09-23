from tests.ui._helpers import make_client


def test_blueprint_list_loads(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/blueprints/")
    assert r.status_code == 200
    assert b"Blueprints" in r.data
