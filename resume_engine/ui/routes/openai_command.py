from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import config_service, openai_command_service

bp = Blueprint("openai_command", __name__, url_prefix="/advanced/openai")


@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    if request.method == "POST":
        try:
            config_service.set_setting(
                "openai_jd_analysis_model",
                request.form.get("openai_jd_analysis_model") or "",
                actor=session.get("username"),
                reason="openai_command_center",
            )
            config_service.set_setting(
                "openai_resume_generation_model",
                request.form.get("openai_resume_generation_model") or "",
                actor=session.get("username"),
                reason="openai_command_center",
            )
            flash("OpenAI model routing saved", "success")
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
        return redirect(url_for("openai_command.index"))

    return render_template(
        "pages/openai_command.html",
        key_status=openai_command_service.openai_key_status(),
        model_options=openai_command_service.model_options(),
        jd_model=config_service.get_effective_setting("openai_jd_analysis_model"),
        resume_model=config_service.get_effective_setting("openai_resume_generation_model"),
        summary=openai_command_service.usage_summary(days=30),
    )
