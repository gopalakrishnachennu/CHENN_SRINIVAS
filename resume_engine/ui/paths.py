"""Filesystem path containment helpers for the operator UI (Gate 4.1)."""

from __future__ import annotations

from pathlib import Path

from resume_engine.config.settings import RUNS_STORAGE_DIR


class InvalidResumePath(ValueError):
    """Raised when a resume path fails containment / validation checks."""


def resolve_validated_resume_path(relative_path: str) -> Path:
    """
    Resolve a candidate resume path and enforce containment.

    Requirements:
    - Resolve to an absolute real path (symlinks followed)
    - Must live under RUNS_STORAGE_DIR
    - Must exist and be a file
    - Must be under a ``validated/`` directory segment
    """
    if not relative_path or not str(relative_path).strip():
        raise InvalidResumePath("empty path")

    raw = str(relative_path).strip()
    # Reject obvious scheme / absolute escapes early.
    if "://" in raw or raw.startswith("\\\\"):
        raise InvalidResumePath("scheme or UNC path not allowed")

    root = RUNS_STORAGE_DIR.resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        # Prefer resolving relative to project runs root via PROJECT_ROOT callers
        # pass project-relative paths; resolve against filesystem CWD-independent root.
        from resume_engine.config.settings import PROJECT_ROOT

        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InvalidResumePath("path outside RUNS_STORAGE_DIR") from exc

    if not candidate.exists():
        raise InvalidResumePath("path does not exist")
    if not candidate.is_file():
        raise InvalidResumePath("path is not a file")

    # Must be under a validated/ directory within the runs tree.
    parts = candidate.parts
    if "validated" not in parts:
        raise InvalidResumePath("path is not under a validated/ directory")
    # Ensure validated segment itself is still under root (already true via relative_to).
    return candidate
