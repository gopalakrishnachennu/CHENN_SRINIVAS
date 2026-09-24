"""Family Registry — Advanced."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import family_registry_service as families

bp = Blueprint("families", __name__, url_prefix="/advanced/families")


@bp.get("/")
@require_auth
def index():
    fams = families.list_families(include_inactive=True)
    return render_template("pages/families.html", families=fams)


@bp.route("/<family_id>", methods=["GET", "POST"])
@require_auth
@csrf_protect
def detail(family_id: str):
    try:
        fam = families.get_family(family_id)
    except KeyError:
        flash("Family not found", "error")
        return redirect(url_for("families.index"))
    if request.method == "POST":
        def split(key):
            return [p.strip() for p in (request.form.get(key) or "").split(",") if p.strip()]
        try:
            families.update_family(
                family_id,
                compatible=split("compatible"),
                hybrid=split("hybrid"),
                blocked=split("blocked"),
                aliases=split("aliases"),
                display_name=request.form.get("display_name"),
                actor=session.get("username"),
            )
            flash("Family updated", "success")
            return redirect(url_for("families.detail", family_id=family_id))
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
        fam = families.get_family(family_id)
    return render_template(
        "pages/family_detail.html",
        family=fam,
        all_families=families.list_families(include_inactive=True),
    )
