"""Lightweight Phase 3 operator UI for browsing validated resumes and exporting DOCX/PDF."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, render_template_string, request, send_file

from resume_engine.config.settings import EXPORT_STORAGE_DIR, PROJECT_ROOT, RUNS_STORAGE_DIR, ensure_storage_dirs
from resume_engine.export.document_model import ContactHeader
from resume_engine.export.service import export_resume, load_resume

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Resume Engine — Phase 3 Export</title>
  <style>
    :root {
      --bg: #f3efe6;
      --ink: #1c1a16;
      --accent: #0f5c4c;
      --card: #fffdf8;
      --line: #d9d0c0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fff8e8, transparent 45%),
        linear-gradient(160deg, #efe7d8, #f7f3ea 55%, #e7efe9);
      min-height: 100vh;
    }
    main { max-width: 980px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
    h1 { font-size: 2rem; margin: 0 0 0.35rem; letter-spacing: -0.02em; }
    .sub { color: #5c564b; margin-bottom: 1.75rem; }
    .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 1.1rem 1.2rem;
      margin-bottom: 1rem;
      box-shadow: 0 10px 30px rgba(40, 30, 10, 0.04);
    }
    .meta { font-size: 0.92rem; color: #5c564b; }
    a { color: var(--accent); }
    .actions { display: flex; flex-wrap: wrap; gap: 0.55rem; margin-top: 0.8rem; }
    .btn {
      appearance: none;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: white;
      border-radius: 999px;
      padding: 0.45rem 0.9rem;
      text-decoration: none;
      font: inherit;
      font-size: 0.92rem;
      cursor: pointer;
    }
    .btn.secondary { background: transparent; color: var(--accent); }
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.65rem 1rem;
    }
    @media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }
    pre {
      white-space: pre-wrap;
      background: #f7f2e8;
      border-radius: 10px;
      padding: 0.9rem;
      overflow: auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.82rem;
    }
    label { display: block; margin: 0.4rem 0 0.2rem; font-size: 0.9rem; }
    input[type=text] {
      width: 100%;
      padding: 0.45rem 0.6rem;
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
      background: white;
    }
  </style>
</head>
<body>
<main>
  <h1>Resume Engine Export</h1>
  <p class="sub">Phase 3 operator UI — browse validated resumes and download DOCX/PDF. No live generation here.</p>

  {% if message %}
  <div class="panel"><strong>{{ message }}</strong></div>
  {% endif %}

  {% if resume %}
  <div class="panel">
    <div class="meta">{{ resume_path }}</div>
    <h2 style="margin:0.4rem 0 0.2rem;">{{ resume.target_title }}</h2>
    <p>{{ resume.summary }}</p>
    <form method="post" action="{{ url_for('export_one') }}">
      <input type="hidden" name="resume_path" value="{{ resume_path }}"/>
      <div class="grid-2">
        <div>
          <label>Candidate name (optional)</label>
          <input type="text" name="candidate_name" placeholder="Name for document header"/>
        </div>
        <div>
          <label>Email (optional)</label>
          <input type="text" name="email" placeholder="email@example.com"/>
        </div>
        <div>
          <label>Phone (optional)</label>
          <input type="text" name="phone" placeholder="+1 …"/>
        </div>
        <div>
          <label>Location (optional)</label>
          <input type="text" name="location" placeholder="City, ST"/>
        </div>
        <div>
          <label>LinkedIn (optional)</label>
          <input type="text" name="linkedin" placeholder="linkedin.com/in/…"/>
        </div>
        <div>
          <label>Website (optional)</label>
          <input type="text" name="website" placeholder="https://…"/>
        </div>
      </div>
      <div class="actions">
        <button class="btn" name="format" value="docx" type="submit">Export DOCX</button>
        <button class="btn" name="format" value="pdf" type="submit">Export PDF</button>
        <button class="btn secondary" name="format" value="both" type="submit">Export both (ZIP)</button>
        <a class="btn secondary" href="{{ url_for('index') }}">Back</a>
      </div>
    </form>
  </div>
  {% else %}
  <div class="panel">
    <h2 style="margin-top:0;">Validated resumes</h2>
    {% if items %}
      {% for item in items %}
      <div style="padding:0.65rem 0; border-top:1px solid var(--line);">
        <div><strong>{{ item.variant_id }}</strong> · {{ item.jd_hash }} / {{ item.run_id }}</div>
        <div class="meta">{{ item.relative }}</div>
        <div class="actions">
          <a class="btn secondary" href="{{ url_for('view_resume', path=item.relative) }}">Open</a>
        </div>
      </div>
      {% endfor %}
    {% else %}
      <p class="meta">No validated resumes found under <code>resume_engine/storage/runs/**/validated/</code>.</p>
    {% endif %}
  </div>
  {% endif %}
</main>
</body>
</html>
"""


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def list_validated_resumes(limit: int = 50) -> list[dict]:
    ensure_storage_dirs()
    root = RUNS_STORAGE_DIR
    if not root.exists():
        return []
    # Stable finals only (Gate 2): ignore attempt_*_final.json clutter.
    files = sorted(
        (
            path
            for path in root.glob("*/*/validated/*_final.json")
            if "_attempt_" not in path.name
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    items = []
    for path in files[:limit]:
        parts = path.parts
        # .../runs/<jd_hash>/<run_id>/validated/<file>
        try:
            runs_idx = parts.index("runs")
            jd_hash = parts[runs_idx + 1]
            run_id = parts[runs_idx + 2]
        except (ValueError, IndexError):
            jd_hash, run_id = "unknown", "unknown"
        items.append(
            {
                "path": path,
                "relative": _relative(path),
                "jd_hash": jd_hash,
                "run_id": run_id,
                "variant_id": path.stem.replace("_final", ""),
            }
        )
    return items


@app.get("/")
def index():
    return render_template_string(PAGE, items=list_validated_resumes(), resume=None, resume_path=None, message=None)


@app.get("/view")
def view_resume():
    rel = request.args.get("path", "")
    path = (PROJECT_ROOT / rel).resolve()
    if not str(path).startswith(str(RUNS_STORAGE_DIR.resolve())) or not path.exists():
        abort(404)
    resume = load_resume(path)
    return render_template_string(
        PAGE,
        items=[],
        resume=resume,
        resume_path=_relative(path),
        message=None,
    )


@app.post("/export")
def export_one():
    import zipfile
    from io import BytesIO

    rel = request.form.get("resume_path", "")
    path = (PROJECT_ROOT / rel).resolve()
    if not str(path).startswith(str(RUNS_STORAGE_DIR.resolve())) or not path.exists():
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


def create_app() -> Flask:
    return app


def main(host: str = "127.0.0.1", port: int = 8765, debug: bool = False) -> None:
    ensure_storage_dirs()
    print(f"Phase 3 UI: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
