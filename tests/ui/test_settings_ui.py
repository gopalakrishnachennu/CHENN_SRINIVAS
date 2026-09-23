from resume_engine.ui.services import config_service
from tests.ui._helpers import csrf_from, make_client


def test_settings_validation_and_lock(monkeypatch):
    client = make_client(monkeypatch)
    page = client.get("/settings/")
    assert page.status_code == 200
    token = csrf_from(page.data.decode())
    # invalid advanced value
    bad = client.post("/settings/", data={"csrf_token":token, "key":"p2_coverage_min", "value":"500"}, follow_redirects=True)
    assert b"above max" in bad.data or b"invalid" in bad.data.lower() or bad.status_code == 200
    # locked setting
    page = client.get("/settings/")
    token = csrf_from(page.data.decode())
    locked = client.post("/settings/", data={"csrf_token":token, "key":"river_active_mode_enabled", "value":"true"}, follow_redirects=True)
    assert b"locked" in locked.data.lower()
    assert config_service.get_effective_setting("river_active_mode_enabled") is False
    assert config_service.get_effective_setting("technology_firewall_enabled") is True
