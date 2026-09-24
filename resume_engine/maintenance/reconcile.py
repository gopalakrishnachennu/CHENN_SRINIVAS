"""Integrity reconciliation for UI SQLite state.

Usage:
  python3 -m resume_engine.maintenance.reconcile --check
  python3 -m resume_engine.maintenance.reconcile --repair
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.blueprint_lifecycle import (
    ANALYSIS_FAILED,
    ANALYSIS_NEEDS,
    ANALYSIS_READY,
    get_analysis_status,
    jd_content_hash,
)
from resume_engine.ui.services.family_registry_service import get_family


def check_integrity() -> dict[str, Any]:
    ensure_ui_schema()
    issues: list[dict[str, Any]] = []
    with connect_ui_db() as conn:
        jobs = conn.execute("SELECT * FROM jd_library").fetchall()
        candidates = conn.execute("SELECT * FROM candidate_profiles").fetchall()
        matches = conn.execute("SELECT * FROM match_cache").fetchall()

    ready = needs = failed = 0
    for row in jobs:
        job = dict(row)
        raw_status = (job.get("analysis_status") or "").upper()
        effective = get_analysis_status({
            "status": job.get("status"),
            "analysis_status": job.get("analysis_status"),
            "blueprint_path": job.get("blueprint_path"),
            "jd_text": job.get("jd_text"),
            "jd_content_hash": job.get("jd_content_hash"),
        })
        path = job.get("blueprint_path")
        # Detect impossible state: DB says READY but blueprint missing/invalid
        if raw_status == ANALYSIS_READY and (not path or not Path(path).exists()):
            issues.append({"code": "READY_MISSING_BLUEPRINT", "job_id": job["id"]})
        if (
            job.get("jd_content_hash")
            and path
            and Path(path).exists()
            and jd_content_hash(job.get("jd_text") or "") != job.get("jd_content_hash")
        ):
            issues.append({"code": "STALE_BLUEPRINT_HASH", "job_id": job["id"]})

        if effective == ANALYSIS_READY:
            ready += 1
        elif effective == ANALYSIS_NEEDS:
            needs += 1
        elif effective == ANALYSIS_FAILED:
            failed += 1

        for fam_key in ("primary_family", "secondary_family"):
            fam = job.get(fam_key)
            if fam and fam not in {"none", "null", ""}:
                try:
                    get_family(fam)
                except KeyError:
                    issues.append({"code": "UNKNOWN_JOB_FAMILY", "job_id": job["id"], "family": fam})

        if path and not Path(path).exists():
            issues.append({"code": "ORPHAN_BLUEPRINT_PATH", "job_id": job["id"], "path": path})

    no_primary = 0
    for row in candidates:
        payload = json.loads(row["payload_json"] or "{}")
        pf = payload.get("primary_family")
        if not pf:
            no_primary += 1
            issues.append({"code": "CANDIDATE_NO_PRIMARY", "candidate_id": row["id"]})
        else:
            try:
                get_family(pf)
            except KeyError:
                issues.append({"code": "UNKNOWN_CANDIDATE_FAMILY", "candidate_id": row["id"], "family": pf})
        sf = payload.get("secondary_family")
        if sf in {"", "None", "null"}:
            issues.append({"code": "SECONDARY_SENTINEL", "candidate_id": row["id"], "value": sf})

    stale_matches = 0
    for m in matches:
        keys = m.keys()
        if "candidate_version" in keys and m["candidate_version"] is not None:
            with connect_ui_db() as conn:
                crow = conn.execute(
                    "SELECT version FROM candidate_profiles WHERE id = ?",
                    (m["candidate_id"],),
                ).fetchone()
            if crow and int(crow["version"] or 1) != int(m["candidate_version"] or 0):
                stale_matches += 1
                issues.append({
                    "code": "STALE_MATCH_CACHE",
                    "candidate_id": m["candidate_id"],
                    "job_id": m["job_id"],
                })

    return {
        "jobs_total": len(jobs),
        "jobs_ready": ready,
        "jobs_needs_analysis": needs,
        "jobs_failed": failed,
        "candidates": len(candidates),
        "candidates_without_primary": no_primary,
        "stale_matches": stale_matches,
        "issue_count": len(issues),
        "issues": issues,
        "ok": len(issues) == 0,
    }


def repair_integrity() -> dict[str, Any]:
    report = check_integrity()
    fixed = []
    ensure_ui_schema()
    with connect_ui_db() as conn:
        for issue in report["issues"]:
            code = issue["code"]
            if code in {"READY_MISSING_BLUEPRINT", "STALE_BLUEPRINT_HASH", "ORPHAN_BLUEPRINT_PATH"}:
                conn.execute(
                    """
                    UPDATE jd_library SET analysis_status = ?, blueprint_path = NULL, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (ANALYSIS_NEEDS, issue["job_id"]),
                )
                fixed.append(issue)
            elif code == "STALE_MATCH_CACHE":
                conn.execute(
                    "DELETE FROM match_cache WHERE candidate_id = ? AND job_id = ?",
                    (issue["candidate_id"], issue["job_id"]),
                )
                fixed.append(issue)
            elif code == "SECONDARY_SENTINEL":
                row = conn.execute(
                    "SELECT payload_json FROM candidate_profiles WHERE id = ?",
                    (issue["candidate_id"],),
                ).fetchone()
                if row:
                    payload = json.loads(row["payload_json"])
                    payload["secondary_family"] = None
                    conn.execute(
                        "UPDATE candidate_profiles SET payload_json = ? WHERE id = ?",
                        (json.dumps(payload), issue["candidate_id"]),
                    )
                    fixed.append(issue)
        conn.commit()
    after = check_integrity()
    return {"fixed": fixed, "before_issues": report["issue_count"], "after": after}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile resume engine UI data integrity")
    parser.add_argument("--check", action="store_true", help="Report only (default)")
    parser.add_argument("--repair", action="store_true", help="Attempt safe repairs")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.repair:
        result = repair_integrity()
    else:
        result = check_integrity()
    print(json.dumps(result, indent=2, default=str))
    if args.repair:
        return 0 if result["after"]["ok"] else 1
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
