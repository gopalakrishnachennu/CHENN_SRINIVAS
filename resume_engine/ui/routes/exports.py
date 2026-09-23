from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, render_template, request, send_file

from resume_engine.config.settings import EXPORT_STORAGE_DIR, PROJECT_ROOT, RUNS_STORAGE_DIR
from resume_engine.ui.auth import require_auth
from resume_engine.ui.paths import InvalidResumePath, resolve_validated_resume_path
from resume_engine.ui.services import export_service_ui

bp = Blueprint("exports", __name__, url_prefix="/exports")

@bp.get("/")
@require_auth
def index():
    return render_template("pages/exports.html", exports=export_service_ui.list_exports())

@bp.get("/download")
@require_auth
def download():
    rel = request.args.get("path") or ""
    try:
        if "/validated/" in rel.replace("\\", "/"):
            path = resolve_validated_resume_path(rel)
        else:
            path = Path(rel)
            if not path.is_absolute():
                path = (PROJECT_ROOT / path).resolve()
            # must be under exports or runs
            ok = False
            for root in (EXPORT_STORAGE_DIR.resolve(), RUNS_STORAGE_DIR.resolve()):
                try:
                    path.relative_to(root)
                    ok = True
                    break
                except ValueError:
                    continue
            if not ok or not path.is_file():
                raise InvalidResumePath("outside allowed roots")
    except InvalidResumePath:
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)
