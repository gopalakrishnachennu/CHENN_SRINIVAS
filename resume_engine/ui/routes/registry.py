from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import registry_service

bp = Blueprint("registry", __name__, url_prefix="/registry")

@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    if request.method == "POST" and request.form.get("action") == "add_alias":
        registry_service.add_alias(
            request.form.get("canonical") or "",
            request.form.get("alias") or "",
            actor=session.get("username"),
        )
        flash("Alias added", "success")
        return redirect(url_for("registry.index"))
    q = request.args.get("q") or ""
    return render_template("pages/registry.html", q=q, technologies=registry_service.search_technologies(q))
