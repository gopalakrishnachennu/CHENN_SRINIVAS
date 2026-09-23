from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import prompt_service

bp = Blueprint("prompts", __name__, url_prefix="/prompts")

@bp.get("/")
@require_auth
def index():
    return render_template("pages/prompts.html", prompts=prompt_service.list_prompts())

@bp.route("/<prompt_id>", methods=["GET", "POST"])
@require_auth
@csrf_protect
def detail(prompt_id: str):
    if request.method == "POST":
        prompt_service.create_version(
            prompt_id,
            request.form.get("content") or "",
            actor=session.get("username"),
            activate=bool(request.form.get("activate")),
        )
        flash("Prompt version created", "success")
        return redirect(url_for("prompts.detail", prompt_id=prompt_id))
    versions = prompt_service.list_versions(prompt_id)
    active_content = ""
    for v in versions:
        if v.get("status") == "ACTIVE":
            active_content = prompt_service.get_version(prompt_id, v["version"])["content"]
            break
    return render_template(
        "pages/prompt_detail.html",
        prompt_id=prompt_id,
        versions=versions,
        active_content=active_content,
    )

@bp.post("/<prompt_id>/activate/<int:version>")
@require_auth
@csrf_protect
def activate(prompt_id: str, version: int):
    prompt_service.activate_version(prompt_id, version, actor=session.get("username"))
    flash("Activated", "success")
    return redirect(url_for("prompts.detail", prompt_id=prompt_id))
