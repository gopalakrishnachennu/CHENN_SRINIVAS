from tests.ui._helpers import csrf_from, make_client


def test_jd_page_loads(monkeypatch):
    client = make_client(monkeypatch)
    r = client.get("/jd/")
    assert r.status_code == 200
    assert b"Analyze JD" in r.data

def test_jd_can_be_submitted_as_draft(monkeypatch):
    client = make_client(monkeypatch)
    page = client.get("/jd/")
    token = csrf_from(page.data.decode())
    r = client.post("/jd/", data={"csrf_token":token, "action":"save_draft", "jd_text":"Senior Engineer\nAWS Terraform"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Draft saved" in r.data or b"JD Workspace" in r.data
