"""Phase 3.1 Resume Intelligence Control Center — Flask application factory."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from resume_engine.config.settings import (
    EXPORT_STORAGE_DIR,
    PROJECT_ROOT,
    ensure_storage_dirs,
    load_local_environment,
)
from resume_engine.export.document_model import ContactHeader
from resume_engine.export.service import export_resume, load_resume
from resume_engine.ui.app_helpers import list_validated_resumes, relative_to_project

# Re-export for existing tests/importers
__all__ = ["app", "create_app", "list_validated_resumes", "main"]
from resume_engine.ui.auth import (
    auth_enabled,
    configure_app_secret,
    is_authenticated,
    login_user,
    logout_user,
    require_auth,
    safe_next_url,
    ui_username,
    verify_credentials,
)
from resume_engine.ui.csrf import ensure_csrf_token, validate_csrf
from resume_engine.ui.db import ensure_ui_schema
from resume_engine.ui.paths import InvalidResumePath, resolve_validated_resume_path
from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.generation_service import get_job


def create_app() -> Flask:
    load_local_environment()
    ensure_storage_dirs()
    ensure_ui_schema()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    configure_app_secret(app)

    @app.context_processor
    def inject_globals():
        return {
            "auth_on": auth_enabled(),
            "csrf_token": ensure_csrf_token(),
            "actor": session.get("username"),
        }

    @app.errorhandler(404)
    def not_found(_err):
        return (
            render_template(
                "pages/error.html",
                message="Resource not found",
                category="not_found",
                run_id=None,
                stage=None,
            ),
            404,
        )

    @app.errorhandler(500)
    def server_error(_err):
        return (
            render_template(
                "pages/error.html",
                message="Internal server error",
                category="server_error",
                run_id=None,
                stage=None,
            ),
            500,
        )

    # --- Auth / health ---
    @app.get("/healthz")
    def healthz():
        return {"ok": True, "auth_enabled": auth_enabled(), "ui": "phase-3.1"}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not auth_enabled():
            return redirect(url_for("dashboard.index"))
        if is_authenticated():
            return redirect(url_for("dashboard.index"))
        error = None
        next_url = safe_next_url(request.values.get("next"), fallback=url_for("dashboard.index"))
        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                error = "Invalid CSRF token."
            else:
                username = request.form.get("username") or ""
                password = request.form.get("password") or ""
                if verify_credentials(username, password):
                    login_user(username)
                    record_audit_event(action="login", actor=username)
                    return redirect(
                        safe_next_url(
                            request.form.get("next") or next_url,
                            fallback=url_for("dashboard.index"),
                        )
                    )
                error = "Invalid username or password."
        ensure_csrf_token()
        return render_template(
            "pages/login.html",
            error=error,
            next_url=next_url,
            default_user=ui_username(),
            csrf_token=ensure_csrf_token(),
        )

    @app.post("/logout")
    def logout():
        if auth_enabled() and not validate_csrf(request.form.get("csrf_token")):
            abort(400)
        actor = session.get("username")
        logout_user()
        record_audit_event(action="logout", actor=actor)
        if auth_enabled():
            return redirect(url_for("login"))
        return redirect(url_for("dashboard.index"))

    # API polling (auth required when enabled)
    @app.get("/api/jobs/<job_id>/status")
    @require_auth
    def api_job_status(job_id: str):
        try:
            return get_job(job_id)
        except KeyError:
            abort(404)

    @app.get("/api/runs/<run_id>/status")
    @require_auth
    def api_run_status(run_id: str):
        # Best-effort: find matching ui_job by run_id
        from resume_engine.ui.services.generation_service import list_jobs

        for job in list_jobs(limit=200):
            if job.get("run_id") == run_id:
                return get_job(job["job_id"])
        return {"run_id": run_id, "status": "UNKNOWN"}

    # Legacy Phase 3 export UI compatibility routes
    @app.get("/legacy/exports")
    @require_auth
    def legacy_exports_index():
        return render_template(
            "pages/exports.html",
            exports=[
                {
                    "path": item["relative"],
                    "name": Path(item["relative"]).name,
                    "suffix": ".json",
                    "size": None,
                }
                for item in list_validated_resumes()
            ],
        )

    @app.get("/view")
    @require_auth
    def view_resume():
        rel = request.args.get("path", "")
        try:
            path = resolve_validated_resume_path(rel)
        except InvalidResumePath:
            abort(404)
        load_resume(path)
        flash(f"Opened {relative_to_project(path)}", "success")
        return redirect(url_for("exports.index"))

    @app.post("/export")
    @require_auth
    def export_one():
        if not validate_csrf(request.form.get("csrf_token")) and auth_enabled():
            abort(400)
        rel = request.form.get("resume_path", "")
        try:
            path = resolve_validated_resume_path(rel)
        except InvalidResumePath:
            abort(404)
        fmt = (request.form.get("format") or "both").lower()
        formats = ("docx", "pdf") if fmt == "both" else (fmt,)
        contact = ContactHeader(
            name=request.form.get("candidate_name") or None,
            email=request.form.get("email") or None,
            phone=request.form.get("phone") or None,
            location=request.form.get("location") or None,
            linkedin=request.form.get("linkedin") or None,
            website=request.form.get("website") or None,
        )
        result = export_resume(
            path,
            formats=formats,
            output_dir=EXPORT_STORAGE_DIR / "ui",
            basename=path.stem,
            contact=contact,
        )
        record_audit_event(
            action="export",
            actor=session.get("username"),
            entity_type="resume",
            entity_id=relative_to_project(path),
            metadata={"formats": list(formats)},
        )
        if fmt == "both":
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for key in ("docx", "pdf"):
                    artifact = result["artifacts"].get(key)
                    if not artifact:
                        continue
                    file_path = PROJECT_ROOT / artifact
                    zf.write(file_path, arcname=file_path.name)
            buffer.seek(0)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"{path.stem}_exports.zip",
                mimetype="application/zip",
            )
        first_fmt = formats[0]
        artifact = result["artifacts"].get(first_fmt)
        if not artifact:
            abort(500)
        file_path = PROJECT_ROOT / artifact
        return send_file(file_path, as_attachment=True, download_name=file_path.name)

    # Register feature blueprints
    from resume_engine.ui.routes import (
        audit,
        blueprints,
        candidates,
        dashboard,
        documents,
        exports,
        generation,
        jd_workspace,
        learning,
        prompts,
        registry,
        repairs,
        runs,
        settings,
        strategies,
        system,
        validation,
    )

    for module in (
        dashboard,
        jd_workspace,
        blueprints,
        candidates,
        strategies,
        generation,
        runs,
        validation,
        repairs,
        learning,
        registry,
        prompts,
        documents,
        exports,
        settings,
        audit,
        system,
    ):
        app.register_blueprint(module.bp)

    return app


# Module-level app for `python -m` / phase_3_export compatibility
app = create_app()


def main(host: str = "127.0.0.1", port: int = 8765, debug: bool = False) -> None:
    ensure_storage_dirs()
    ensure_ui_schema()
    mode = "password-protected" if auth_enabled() else "open (no RESUME_ENGINE_UI_PASSWORD)"
    print(f"Phase 3.1 Control Center ({mode}): http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
