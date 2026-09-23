
from __future__ import annotations

import re

from resume_engine.ui.app import create_app


def make_client(monkeypatch, *, password: str | None = None):
    monkeypatch.delenv("RESUME_ENGINE_UI_PASSWORD", raising=False)
    if password:
        monkeypatch.setenv("RESUME_ENGINE_UI_PASSWORD", password)
        monkeypatch.setenv("RESUME_ENGINE_UI_USER", "operator")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()

def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "missing csrf"
    return match.group(1)

def login(client, password="s3cret"):
    page = client.get("/login")
    token = csrf_from(page.data.decode())
    return client.post("/login", data={"username":"operator","password":password,"csrf_token":token,"next":"/"}, follow_redirects=True)
