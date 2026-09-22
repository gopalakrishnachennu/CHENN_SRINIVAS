"""Run-scoped artifact storage for Phase 2.6 Wave 1."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from resume_engine.config.settings import (
    PROMPT_VERSION,
    PROJECT_ROOT,
    RUNS_STORAGE_DIR,
    ensure_storage_dirs,
    portable_path,
)
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy
from resume_engine.models.validation_schema import ValidationBundle
from resume_engine.reports.resume_validation_report import build_resume_validation_text


@dataclass
class RunPaths:
    run_id: str
    jd_hash: str
    root: Path

    @property
    def metadata_path(self) -> Path:
        return self.root / "metadata.json"

    @property
    def strategy_dir(self) -> Path:
        return self.root / "strategy"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def repaired_dir(self) -> Path:
        return self.root / "repaired"

    @property
    def validated_dir(self) -> Path:
        return self.root / "validated"

    @property
    def rejected_dir(self) -> Path:
        return self.root / "rejected"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"


def generate_run_id(explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    return str(uuid.uuid4())


def create_run_paths(jd_hash: str, run_id: str | None = None) -> RunPaths:
    ensure_storage_dirs()
    resolved_run_id = generate_run_id(run_id)
    root = RUNS_STORAGE_DIR / jd_hash / resolved_run_id
    paths = RunPaths(run_id=resolved_run_id, jd_hash=jd_hash, root=root)
    for directory in [
        paths.strategy_dir,
        paths.raw_dir,
        paths.repaired_dir,
        paths.validated_dir,
        paths.rejected_dir,
        paths.reports_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def write_run_metadata(paths: RunPaths, metadata: dict) -> Path:
    payload = {
        "run_id": paths.run_id,
        "jd_hash": paths.jd_hash,
        "prompt_version": PROMPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **metadata,
    }
    with open(paths.metadata_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return paths.metadata_path


def save_strategy_artifact(paths: RunPaths, strategy: ResumeStrategy) -> Path:
    path = paths.strategy_dir / "strategy.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(strategy.model_dump(), f, indent=2, ensure_ascii=False)
    return path


def save_resume_artifact(directory: Path, filename: str, resume: ResumeJSON) -> Path:
    path = directory / filename
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing artifact: {portable_path(path)}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resume.model_dump(), f, indent=2, ensure_ascii=False)
    return path


def next_repair_filename(paths: RunPaths, variant_id: str) -> str:
    index = 1
    while True:
        name = f"{variant_id}_repair_{index:02d}.json"
        if not (paths.repaired_dir / name).exists():
            return name
        index += 1


def save_raw_resume(
    paths: RunPaths,
    variant_id: str,
    resume: ResumeJSON,
    *,
    versioned_if_exists: bool = True,
) -> Path:
    name = f"{variant_id}_raw.json"
    path = paths.raw_dir / name
    if path.exists() and versioned_if_exists:
        index = 1
        while True:
            candidate = paths.raw_dir / f"{variant_id}_raw_regen_{index:02d}.json"
            if not candidate.exists():
                return save_resume_artifact(paths.raw_dir, candidate.name, resume)
            index += 1
    return save_resume_artifact(paths.raw_dir, name, resume)


def save_repaired_resume(paths: RunPaths, variant_id: str, resume: ResumeJSON) -> Path:
    return save_resume_artifact(paths.repaired_dir, next_repair_filename(paths, variant_id), resume)


def save_validated_resume_artifact(
    paths: RunPaths,
    variant_id: str,
    resume: ResumeJSON,
    *,
    versioned_if_exists: bool = True,
) -> Path:
    name = f"{variant_id}_final.json"
    path = paths.validated_dir / name
    if path.exists() and versioned_if_exists:
        index = 1
        while True:
            candidate = paths.validated_dir / f"{variant_id}_final_regen_{index:02d}.json"
            if not candidate.exists():
                return save_resume_artifact(paths.validated_dir, candidate.name, resume)
            index += 1
    return save_resume_artifact(paths.validated_dir, name, resume)


def save_rejected_resume_artifact(
    paths: RunPaths,
    variant_id: str,
    resume: ResumeJSON,
    *,
    versioned_if_exists: bool = True,
) -> Path:
    name = f"{variant_id}_rejected.json"
    path = paths.rejected_dir / name
    if path.exists() and versioned_if_exists:
        index = 1
        while True:
            candidate = paths.rejected_dir / f"{variant_id}_rejected_regen_{index:02d}.json"
            if not candidate.exists():
                return save_resume_artifact(paths.rejected_dir, candidate.name, resume)
            index += 1
    return save_resume_artifact(paths.rejected_dir, name, resume)


def save_validation_bundle_reports(
    paths: RunPaths,
    blueprint,
    bundle: ValidationBundle,
    stage: str,
) -> tuple[Path, Path]:
    stem = f"{bundle.variant_id}_{stage}_validation"
    json_path = paths.reports_dir / f"{stem}.json"
    txt_path = paths.reports_dir / f"{stem}.txt"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(bundle.model_dump(), f, indent=2, ensure_ascii=False)
    txt_path.write_text(build_resume_validation_text(blueprint, bundle), encoding="utf-8")
    return json_path, txt_path


def relative(path: Path | str | None) -> str | None:
    return portable_path(path)
