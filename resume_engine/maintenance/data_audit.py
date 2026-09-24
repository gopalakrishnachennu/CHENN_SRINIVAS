"""Production data audit and safe test-contamination cleanup.

Usage:
  python3 -m resume_engine.maintenance.data_audit --check
  python3 -m resume_engine.maintenance.data_audit --backup
  python3 -m resume_engine.maintenance.data_audit --clean-test-contamination --dry-run
  python3 -m resume_engine.maintenance.data_audit --clean-test-contamination
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_engine.config.settings import production_sqlite_db_path
from resume_engine.ui.services.blueprint_lifecycle import jd_content_hash

KNOWN_TEST_CANDIDATE_NAMES = {
    "UI Cand A",
    "UI Cand B",
    "UI Cand C",
    "UI Cand D",
    "UI Cand E",
    "UI Cand F",
    "UI Cand G",
    "UI Cand H",
    "E2E Cand",
    "Import Cand",
    "SF Only",
    "Arch Cand",
    "No Co",
    "Test Candidate UI",
    "Dup",
    "S",
    "Isolation Probe",
    "UI Cand Isolation",
    "Strict Batch",
    "UI Cand Page",
    "UI Cand Compat",
}

KNOWN_TEST_JOB_TITLES = {
    "Pending AI Role",
    "Pending Only Role",
    "Prep Role",
    "Pending",
    "Test Role",
    "Imported Role",
    "Dedupe Role",
}

TEST_NAME_PREFIXES = (
    "UI Cand ",
    "E2E ",
    "Test Candidate",
    "Import Cand",
    "Isolation ",
    "Strict ",
)

TEST_TITLE_PREFIXES = (
    "Pending ",
    "Prep Role",
)


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_likely_test_candidate(name: str) -> bool:
    n = (name or "").strip()
    if n in KNOWN_TEST_CANDIDATE_NAMES:
        return True
    return any(n.startswith(p) for p in TEST_NAME_PREFIXES)


def _is_likely_test_job(title: str, blueprint_path: str | None = None) -> bool:
    t = (title or "").strip()
    if t in KNOWN_TEST_JOB_TITLES:
        return True
    if any(t.startswith(p) for p in TEST_TITLE_PREFIXES):
        return True
    return bool(blueprint_path and "test_blueprints" in str(blueprint_path))


def _open_production_conn() -> sqlite3.Connection:
    path = production_sqlite_db_path()
    if not path.exists():
        raise FileNotFoundError(f"production DB missing: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def audit_check(*, use_production: bool = True) -> dict[str, Any]:
    """Read-only audit of the production SQLite file."""
    _ = use_production
    return _audit_check_inner()


def _audit_check_inner() -> dict[str, Any]:
    path = production_sqlite_db_path()
    if not path.exists():
        return {
            "db_path": str(path),
            "db_sha256": None,
            "candidates": 0,
            "active_jobs": 0,
            "archived_jobs": 0,
            "ready_jobs": 0,
            "needs_analysis_jobs": 0,
            "likely_test_candidates": [],
            "likely_test_jobs": [],
            "contamination_count": 0,
            "ok_no_test_contamination": True,
            "note": "production DB does not exist",
        }

    conn = _open_production_conn()
    try:
        candidates = conn.execute("SELECT * FROM candidate_profiles").fetchall()
        jobs = conn.execute("SELECT * FROM jd_library").fetchall()
    finally:
        conn.close()

    active_jobs = [j for j in jobs if (j["status"] or "") != "archived"]
    archived_jobs = [j for j in jobs if (j["status"] or "") == "archived"]
    ready = [j for j in active_jobs if (j["analysis_status"] or "").upper() == "READY"]
    needs = [j for j in active_jobs if (j["analysis_status"] or "").upper() == "NEEDS_ANALYSIS"]

    by_source = Counter((j["source"] or "unknown") for j in active_jobs)
    by_company = Counter((j["company"] or "(none)") for j in active_jobs)
    by_analysis = Counter((j["analysis_status"] or "UNKNOWN") for j in active_jobs)

    by_hash: dict[str, list[str]] = defaultdict(list)
    by_url: dict[str, list[str]] = defaultdict(list)
    by_title_co: dict[str, list[str]] = defaultdict(list)
    by_text: dict[str, list[str]] = defaultdict(list)
    for j in jobs:
        if j["jd_content_hash"]:
            by_hash[j["jd_content_hash"]].append(j["id"])
        elif j["jd_text"]:
            by_text[jd_content_hash(j["jd_text"])].append(j["id"])
        if j["job_url"]:
            by_url[str(j["job_url"]).strip()].append(j["id"])
        key = f"{(j['title'] or '').strip().lower()}|{(j['company'] or '').strip().lower()}"
        by_title_co[key].append(j["id"])

    def dups(mapping):
        return {k: v for k, v in mapping.items() if len(v) > 1}

    test_candidates = [
        {"id": c["id"], "name": c["name"]}
        for c in candidates
        if _is_likely_test_candidate(c["name"] or "")
    ]
    test_jobs = []
    test_blueprint_jobs = []
    for j in jobs:
        if _is_likely_test_job(j["title"] or "", j["blueprint_path"]):
            test_jobs.append(
                {"id": j["id"], "title": j["title"], "blueprint_path": j["blueprint_path"]}
            )
        if j["blueprint_path"] and "test_blueprints" in str(j["blueprint_path"]):
            test_blueprint_jobs.append({"id": j["id"], "path": j["blueprint_path"]})

    return {
        "db_path": str(path),
        "db_sha256": sha256_file(path),
        "candidates": len(candidates),
        "active_jobs": len(active_jobs),
        "archived_jobs": len(archived_jobs),
        "ready_jobs": len(ready),
        "needs_analysis_jobs": len(needs),
        "jobs_by_source": dict(by_source),
        "jobs_by_company": dict(by_company.most_common(30)),
        "jobs_by_analysis_status": dict(by_analysis),
        "duplicate_content_hash": dups(by_hash) or dups(by_text),
        "duplicate_job_url": dups(by_url),
        "duplicate_title_company": {k: v for k, v in dups(by_title_co).items() if k != "|"},
        "likely_test_candidates": test_candidates,
        "likely_test_jobs": test_jobs,
        "test_blueprint_jobs": test_blueprint_jobs,
        "known_test_strings_present": {
            "candidates": [c["name"] for c in test_candidates],
            "jobs": [j["title"] for j in test_jobs],
        },
        "contamination_count": len(test_candidates) + len(test_jobs),
        "ok_no_test_contamination": len(test_candidates) == 0 and len(test_jobs) == 0,
    }


def backup_production_db() -> dict[str, Any]:
    src = production_sqlite_db_path()
    if not src.exists():
        return {"ok": False, "error": "production DB missing", "path": str(src)}
    dest_dir = src.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"resume_engine.sqlite3.bak.{_now_stamp()}"
    shutil.copy2(src, dest)
    return {
        "ok": True,
        "source": str(src),
        "backup": str(dest),
        "sha256": sha256_file(dest),
    }


def _clean_targets(report: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "candidate_ids": [c["id"] for c in report.get("likely_test_candidates") or []],
        "job_ids": [j["id"] for j in report.get("likely_test_jobs") or []],
    }


def clean_test_contamination(*, dry_run: bool = True) -> dict[str, Any]:
    """Remove only confidently identified test rows from the production DB."""
    report = _audit_check_inner()
    targets = _clean_targets(report)
    plan: dict[str, Any] = {
        "dry_run": dry_run,
        "candidates_to_remove": report.get("likely_test_candidates") or [],
        "jobs_to_remove": report.get("likely_test_jobs") or [],
        "candidate_ids": targets["candidate_ids"],
        "job_ids": targets["job_ids"],
    }
    if dry_run:
        plan["ok"] = True
        plan["deleted"] = False
        return plan

    path = production_sqlite_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        for cid in targets["candidate_ids"]:
            conn.execute("DELETE FROM match_cache WHERE candidate_id = ?", (cid,))
            conn.execute("DELETE FROM resume_library WHERE candidate_id = ?", (cid,))
            conn.execute("DELETE FROM resume_runs WHERE candidate_id = ?", (cid,))
            conn.execute("DELETE FROM candidate_profile_versions WHERE profile_id = ?", (cid,))
            conn.execute("DELETE FROM candidate_profiles WHERE id = ?", (cid,))
            try:
                conn.execute(
                    "DELETE FROM audit_events WHERE entity_type = 'candidate' AND entity_id = ?",
                    (cid,),
                )
            except sqlite3.OperationalError:
                pass
        for jid in targets["job_ids"]:
            conn.execute("DELETE FROM match_cache WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM resume_library WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM resume_runs WHERE jd_id = ?", (jid,))
            conn.execute("DELETE FROM jd_library WHERE id = ?", (jid,))
            try:
                conn.execute(
                    "DELETE FROM audit_events WHERE entity_type IN ('jd','jd_library') AND entity_id = ?",
                    (jid,),
                )
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()

    after = _audit_check_inner()
    plan["deleted"] = True
    plan["after"] = {
        "candidates": after["candidates"],
        "active_jobs": after["active_jobs"],
        "contamination_count": after["contamination_count"],
        "ok_no_test_contamination": after["ok_no_test_contamination"],
    }
    plan["ok"] = True
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report only (default)")
    parser.add_argument("--backup", action="store_true", help="Timestamped SQLite backup")
    parser.add_argument(
        "--clean-test-contamination",
        action="store_true",
        help="Remove confidently identified test rows",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned deletions only")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.backup:
        result = backup_production_db()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1

    if args.clean_test_contamination:
        result = clean_test_contamination(dry_run=bool(args.dry_run))
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1

    result = audit_check()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
