from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services import generation_service
from tests.ui._helpers import make_client


def test_generation_job_created_without_running_pipeline(monkeypatch):
    # stub executor work by patching _run_job no-op after insert
    calls = {}
    def fake_run(job_id):
        calls["job_id"] = job_id
        generation_service._update(job_id, status="COMPLETED", stage="stubbed", result={"ok": True})
    monkeypatch.setattr(generation_service, "_run_job", fake_run)
    # Also prevent executor from using real function — create job submits to executor
    # Override executor submit
    class FakeFuture:
        def __init__(self, fn, *a, **k):
            fn(*a, **k)
    monkeypatch.setattr(generation_service._EXECUTOR, "submit", lambda fn, *a, **k: FakeFuture(fn, *a, **k))

    job = generation_service.create_generation_job({
        "blueprint_path": "resume_engine_data/blueprints/missing.json",
        "variant_count": 1,
    }, actor="test")
    assert job["status"] in {"QUEUED", "RUNNING", "COMPLETED", "FAILED"}
    fetched = generation_service.get_job(job["job_id"])
    assert fetched["job_id"] == job["job_id"]

def test_run_progress_endpoint(monkeypatch):
    client = make_client(monkeypatch)
    ensure_ui_schema()
    # insert a fake job row directly
    import uuid
    from datetime import UTC, datetime
    jid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with connect_ui_db() as conn:
        conn.execute("INSERT INTO ui_jobs(job_id, run_id, status, stage, payload_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                     (jid, "run-x", "RUNNING", "phase2", "{}", now, now))
        conn.commit()
    r = client.get(f"/api/jobs/{jid}/status")
    assert r.status_code == 200
    assert r.get_json()["status"] == "RUNNING"
