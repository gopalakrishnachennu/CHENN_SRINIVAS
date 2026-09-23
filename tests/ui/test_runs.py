from tests.ui._helpers import make_client


def test_run_list_works(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/runs/")
    assert r.status_code == 200
    assert b"Runs" in r.data
