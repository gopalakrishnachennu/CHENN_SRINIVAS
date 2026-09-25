"""Export a zero-API resume draft from the verified master profile and local JD."""

from __future__ import annotations

import hashlib
import json
import uuid

from resume_engine.config.settings import PROJECT_ROOT
from resume_engine.generation.fact_draft import create_fact_draft
from resume_engine.ui.services.candidate_service import to_engine_candidate_profile

from scripts.import_master_candidate import master_to_candidate


def main() -> None:
    master = json.loads((PROJECT_ROOT / "candidate_profile.json").read_text(encoding="utf-8"))
    jd_text = (PROJECT_ROOT / "real_jd.txt").read_text(encoding="utf-8").strip()
    target_title = jd_text.splitlines()[0].strip()
    if not target_title:
        raise ValueError("The local JD must begin with a target job title.")

    candidate = to_engine_candidate_profile(master_to_candidate(master))
    snapshot_dir = PROJECT_ROOT / "resume_engine" / "storage" / "ui" / "candidate_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / "master_verified.json"
    snapshot_path.write_text(json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8")

    result = create_fact_draft(
        target_title=target_title,
        jd_hash=hashlib.sha256(jd_text.encode("utf-8")).hexdigest()[:32],
        candidate_profile_path=snapshot_path,
        run_id=str(uuid.uuid4()),
        formats=["docx", "pdf"],
    )
    print(json.dumps({
        "run_id": result["run_id"],
        "summary_path": result["summary_path"],
        "evidence_gaps": result["evidence_gaps"],
        "artifacts": result["exports"][0]["artifacts"],
        "openai_requests": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
