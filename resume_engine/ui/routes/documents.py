from __future__ import annotations

from flask import Blueprint, render_template

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import document_service

bp = Blueprint("documents", __name__, url_prefix="/documents")

@bp.get("/")
@require_auth
def index():
    return render_template("pages/documents.html", templates=document_service.list_templates())
