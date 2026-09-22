"""Run-scoped artifact storage with immutable run roots (Gate 1)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from resume_engine.config.settings import (
    PROMPT_VERSION,
    RUNS_STORAGE_DIR,
    ensure_storage_dirs,
    portable_path,
)
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy
from resume_engine.models.validation_schema import ValidationBundle
from resume_engine.reports.resume_validation_report import build_resume_validation_text

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class InvalidRunIdError(ValueError):
    """Raised when an explicit run_id is empty, unsafe, or malformed."""


class RunAlreadyExistsError(FileExistsError):
    """Raised when storage/runs/<jd_hash>/<run_id>/ already exists."""


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


def validate_run_id(explicit: str) -> str:
    if explicit is None or not str(explicit).strip():
        raise InvalidRunIdError("run_id must be a non-empty string")
    raw = str(explicit)
    if raw.strip() != raw:
        raise InvalidRunIdError("run_id must not include leading/trailing whitespace")
    if raw in {".", ".."}:
        raise InvalidRunIdError("run_id must not be '.' or '..'")
    if "/" in raw or "\\" in raw or ".." in raw:
        raise InvalidRunIdError("run_id must not contain path separators or parent traversal")
    if len(raw) > 64:
        raise InvalidRunIdError("run_id must be at most 64 characters")
    if not RUN_ID_PATTERN.fullmatch(raw):
        raise InvalidRunIdError("run_id must match ^[A-Za-z0-9_-]{1,64}$")
    return raw


def generate_run_id(explicit: str | None = None) -> str:
    if explicit is not None:
        return validate_run_id(explicit)
    return str(uuid.uuid4())


def create_run_paths(jd_hash: str, run_id: str | None = None) -> RunPaths:
    ensure_storage_dirs()
    resolved_run_id = generate_run_id(run_id)
    root = RUNS_STORAGE_DIR / jd_hash / resolved_run_id
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise RunAlreadyExistsError(
            f"Run already exists and is immutable: {portable_path(root)}"
        ) from exc

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
    if paths.metadata_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing run metadata: {portable_path(paths.metadata_path)}"
        )
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
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing strategy: {portable_path(path)}")
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
    attempt_no: int = 1,
    versioned_if_exists: bool = True,
) -> Path:
    name = f"{variant_id}_attempt_{attempt_no:02d}_raw.json"
    path = paths.raw_dir / name
    if path.exists() and versioned_if_exists:
        index = attempt_no
        while True:
            candidate = paths.raw_dir / f"{variant_id}_attempt_{index:02d}_raw.json"
            if not candidate.exists():
                return save_resume_artifact(paths.raw_dir, candidate.name, resume)
            index += 1
    return save_resume_artifact(paths.raw_dir, name, resume)


def save_repaired_resume(
    paths: RunPaths,
    variant_id: str,
    resume: ResumeJSON,
    *,
    attempt_no: int = 1,
) -> Path:
    name = f"{variant_id}_attempt_{attempt_no:02d}_repair_{next_repair_filename(paths, variant_id).split('_repair_')[-1]}"
    # Prefer stable attempt-scoped name.
    name = f"{variant_id}_attempt_{attempt_no:02d}_repair.json"
    path = paths.repaired_dir / name
    if path.exists():
        index = 1
        while True:
            candidate = paths.repaired_dir / f"{variant_id}_attempt_{attempt_no:02d}_repair_{index:02d}.json"
            if not candidate.exists():
                return save_resume_artifact(paths.repaired_dir, candidate.name, resume)
            index += 1
    return save_resume_artifact(paths.repaired_dir, name, resume)


def save_validated_resume_artifact(
    paths: RunPaths,
    variant_id: str,
    resume: ResumeJSON,
    *,
    attempt_no: int = 1,
    versioned_if_exists: bool = True,
) -> Path:
    # Final selected artifact keeps stable name; attempt copy preserved separately when regenerating.
    attempt_name = f"{variant_id}_attempt_{attempt_no:02d}_final.json"
    save_resume_artifact(paths.validated_dir, attempt_name, resume)

    name = f"{variant_id}_final.json"
    path = paths.validated_dir / name
    if path.exists():
        if not versioned_if_exists:
            raise FileExistsError(f"Refusing to overwrite existing artifact: {portable_path(path)}")
        # Move prior final aside is not needed — attempt files already preserve history.
        # Replace symlink-like pointer by writing a selection marker instead of overwrite.
        marker = paths.validated_dir / f"{variant_id}_final_selected_attempt.json"
        with open(marker, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "variant_id": variant_id,
                    "attempt_no": attempt_no,
                    "artifact": attempt_name,
                },
                f,
                indent=2,
            )
        return paths.validated_dir / attempt_name
    return save_resume_artifact(paths.validated_dir, name, resume)


def save_rejected_resume_artifact(
    paths: RunPaths,
    variant_id: str,
    resume: ResumeJSON,
    *,
    attempt_no: int = 1,
    versioned_if_exists: bool = True,
) -> Path:
    name = f"{variant_id}_attempt_{attempt_no:02d}_rejected.json"
    path = paths.rejected_dir / name
    if path.exists() and versioned_if_exists:
        index = 1
        while True:
            candidate = paths.rejected_dir / f"{variant_id}_attempt_{attempt_no:02d}_rejected_{index:02d}.json"
            if not candidate.exists():
                return save_resume_artifact(paths.rejected_dir, candidate.name, resume)
            index += 1
    return save_resume_artifact(paths.rejected_dir, name, resume)


def save_validation_bundle_reports(
    paths: RunPaths,
    blueprint,
    bundle: ValidationBundle,
    stage: str,
    *,
    attempt_no: int = 1,
) -> tuple[Path, Path]:
    attempt_dir = paths.reports_dir / bundle.variant_id / f"attempt_{attempt_no:02d}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{stage}_validation"
    json_path = attempt_dir / f"{stem}.json"
    txt_path = attempt_dir / f"{stem}.txt"
    if json_path.exists() or txt_path.exists():
        # Never silently overwrite attempt evidence.
        index = 1
        while True:
            json_candidate = attempt_dir / f"{stem}_{index:02d}.json"
            txt_candidate = attempt_dir / f"{stem}_{index:02d}.txt"
            if not json_candidate.exists() and not txt_candidate.exists():
                json_path, txt_path = json_candidate, txt_candidate
                break
            index += 1
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(bundle.model_dump(), f, indent=2, ensure_ascii=False)
    txt_path.write_text(build_resume_validation_text(blueprint, bundle), encoding="utf-8")
    return json_path, txt_path


def save_pipeline_error_report(
    paths: RunPaths,
    *,
    variant_id: str,
    stage: str,
    error: BaseException,
    attempt_no: int = 1,
) -> Path:
    report_dir = paths.reports_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{variant_id}_pipeline_error.json"
    if path.exists():
        index = 1
        while True:
            candidate = report_dir / f"{variant_id}_pipeline_error_{index:02d}.json"
            if not candidate.exists():
                path = candidate
                break
            index += 1
    payload = {
        "variant_id": variant_id,
        "status": "PIPELINE_ERROR",
        "stage": stage,
        "attempt_no": attempt_no,
        "error_type": type(error).__name__,
        "error_code": getattr(error, "code", type(error).__name__),
        "message": str(error)[:2000],
        "passed": False,
        "eligible_for_learning": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def relative(path: Path | str | None) -> str | None:
    return portable_path(path)
