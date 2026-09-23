from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, abort, render_template, request, send_file

from resume_engine.config.settings import PROJECT_ROOT, RUNS_STORAGE_DIR
from resume_engine.ui.auth import require_auth
from resume_engine.ui.paths import InvalidResumePath, resolve_validated_resume_path
from resume_engine.ui.services import run_service

bp = Blueprint("runs", __name__, url_prefix="/runs")

@bp.get("/")
@require_auth
def index():
    filters = {
        "jd": request.args.get("jd") or "",
        "run_id": request.args.get("run_id") or "",
        "status": request.args.get("status") or "",
    }
    return render_template("pages/runs.html", runs=run_service.list_runs(**filters), filters=filters)

@bp.get("/<jd_hash>/<run_id>")
@require_auth
def detail(jd_hash: str, run_id: str):
    try:
        data = run_service.get_run(jd_hash, run_id)
    except FileNotFoundError:
        abort(404)
    summary = data["summary"]
    variants = summary.get("variant_results") or summary.get("variants") or []
    return render_template(
        "pages/run_detail.html",
        jd_hash=jd_hash,
        run_id=run_id,
        summary=summary,
        variants=variants,
        artifacts_json=json.dumps(data["artifacts"], indent=2),
    )

@bp.get("/artifact")
@require_auth
def artifact():
    rel = request.args.get("path") or ""
    # Prefer validated containment when under validated/
    try:
        if "validated" in rel.replace("\\", "/"):
            path = resolve_validated_resume_path(rel)
        else:
            path = Path(rel)
            if not path.is_absolute():
                path = (PROJECT_ROOT / path).resolve()
            path.relative_to(RUNS_STORAGE_DIR.resolve())
            if not path.is_file():
                abort(404)
    except (InvalidResumePath, ValueError):
        abort(404)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return render_template("pages/error.html", message="JSON artifact", category="artifact", run_id=None, stage=None) if False else (
            __import__("flask").Response(json.dumps(data, indent=2), mimetype="application/json")
        )
    return send_file(path, as_attachment=True, download_name=path.name)
