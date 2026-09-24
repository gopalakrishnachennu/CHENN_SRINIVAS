#!/usr/bin/env python3
"""Batch real JD → Phase1 → Phase2 shadow collection. Never sets active or --train."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

os.environ["RESUME_ONLINE_LEARNING_MODE"] = "shadow"

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
LOG = ROOT / "logs" / "shadow_collection"
BATCH = ROOT / "real_jds_batch"
STATUS = LOG / "batch_status.jsonl"
TARGET = 50
LOG.mkdir(parents=True, exist_ok=True)

manifest = [
    Path(p)
    for p in (BATCH / "MANIFEST.txt").read_text().splitlines()
    if p.strip() and "18_Mock" not in p
]


def metrics() -> dict:
    from resume_engine.learning.online.evaluator import build_shadow_evaluation

    ev = build_shadow_evaluation()
    return {
        "eligible_observations": ev.eligible_observations,
        "linked_observations": ev.linked_observations,
        "total_decisions": ev.total_decisions,
        "insufficient_evidence": ev.insufficient_evidence,
        "activation_ready": ev.activation_ready,
        "mean_reward_all": ev.mean_reward_all,
        "shadow_agreement_rate": ev.shadow_agreement_rate,
    }


def log_status(row: dict) -> None:
    with STATUS.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str), flush=True)


def main() -> int:
    m0 = metrics()
    log_status(
        {
            "event": "batch_start",
            "ts": datetime.now(UTC).isoformat(),
            "metrics": m0,
            "n_jds": len(manifest),
            "mode": os.environ.get("RESUME_ONLINE_LEARNING_MODE"),
        }
    )

    for idx, jd_path in enumerate(manifest, 1):
        m = metrics()
        if int(m.get("eligible_observations") or 0) >= TARGET:
            log_status({"event": "target_reached", "metrics": m})
            break

        real_jd = ROOT / "real_jd.txt"
        shutil.copy2(jd_path, real_jd)
        tag = jd_path.stem
        phase1_log = LOG / f"{idx:02d}_{tag}_phase1.txt"
        phase2_log = LOG / f"{idx:02d}_{tag}_phase2.txt"
        log_status(
            {
                "event": "jd_start",
                "idx": idx,
                "jd": str(jd_path),
                "eligible_before": m.get("eligible_observations"),
            }
        )

        try:
            with phase1_log.open("w") as f:
                r1 = subprocess.run(
                    [sys.executable, "jd_blueprint_engine.py", "--jd-file", str(real_jd)],
                    cwd=ROOT,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            if r1.returncode != 0:
                log_status(
                    {"event": "phase1_fail", "idx": idx, "jd": tag, "code": r1.returncode}
                )
                continue

            blueprints = sorted(
                (ROOT / "resume_engine_data" / "blueprints").glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not blueprints:
                log_status({"event": "no_blueprint", "idx": idx, "jd": tag})
                continue
            blueprint = blueprints[0]

            with phase2_log.open("w") as f:
                r2 = subprocess.run(
                    [
                        sys.executable,
                        "phase_2_resume_pipeline.py",
                        "--blueprint",
                        str(blueprint),
                        "--candidate-profile",
                        "candidate_profile.json",
                        "--variants",
                        "5",
                        "--audit",
                        "--behavioral-audit",
                        "--export",
                        "docx,pdf",
                    ],
                    cwd=ROOT,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

            online = None
            passed = None
            try:
                text = phase2_log.read_text(errors="replace")
                msum = re.search(r'"summary_path": "([^"]+)"', text)
                if msum:
                    summary = json.loads(Path(msum.group(1)).read_text())
                    online = summary.get("online_learning")
                    variants = summary.get("variants") or summary.get("variant_results") or []
                    if isinstance(variants, list):
                        passed = sum(
                            1
                            for v in variants
                            if isinstance(v, dict) and v.get("passed")
                        )
            except Exception as e:  # noqa: BLE001
                online = {"parse_error": str(e)}

            m2 = metrics()
            log_status(
                {
                    "event": "jd_done",
                    "idx": idx,
                    "jd": tag,
                    "phase2_code": r2.returncode,
                    "passed_variants": passed,
                    "online": online,
                    "metrics": m2,
                }
            )
        except Exception as e:  # noqa: BLE001
            log_status(
                {
                    "event": "jd_exception",
                    "idx": idx,
                    "jd": tag,
                    "error": str(e),
                    "tb": traceback.format_exc()[-1000:],
                }
            )

    m_final = metrics()
    subprocess.run(
        [sys.executable, "-m", "resume_engine.learning.online.evaluator", "--write-report"],
        cwd=ROOT,
    )
    subprocess.run(
        [sys.executable, "-m", "resume_engine.learning.online.replay", "--dry-run"],
        cwd=ROOT,
    )
    log_status(
        {
            "event": "batch_complete",
            "ts": datetime.now(UTC).isoformat(),
            "metrics": m_final,
        }
    )
    print("BATCH_COMPLETE", m_final, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
