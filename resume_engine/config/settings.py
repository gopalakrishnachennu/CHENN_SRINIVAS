from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = PROJECT_ROOT / "resume_engine" / "storage"
RUNS_STORAGE_DIR = STORAGE_DIR / "runs"

# Legacy flat directories retained for backward-compatible reads of prior artifacts.
BLUEPRINT_STORAGE_DIR = STORAGE_DIR / "blueprints"
STRATEGY_STORAGE_DIR = STORAGE_DIR / "strategies"
GENERATED_STORAGE_DIR = STORAGE_DIR / "generated"
VALIDATED_STORAGE_DIR = STORAGE_DIR / "validated"
REJECTED_STORAGE_DIR = STORAGE_DIR / "rejected"
REPORT_STORAGE_DIR = STORAGE_DIR / "reports"
LEARNING_STORAGE_DIR = STORAGE_DIR / "learning"
DB_STORAGE_DIR = STORAGE_DIR / "db"
SQLITE_DB_PATH = DB_STORAGE_DIR / "resume_engine.sqlite3"
EXPORT_STORAGE_DIR = STORAGE_DIR / "exports"

DEFAULT_OPENAI_MODEL = "gpt-5.6"
DEFAULT_VARIANT_COUNT = 5
PROMPT_VERSION = "phase2_wave4_v1"


def load_local_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env.local")
    load_dotenv(PROJECT_ROOT / ".env")


def ensure_storage_dirs() -> None:
    for path in [
        BLUEPRINT_STORAGE_DIR,
        STRATEGY_STORAGE_DIR,
        GENERATED_STORAGE_DIR,
        VALIDATED_STORAGE_DIR,
        REJECTED_STORAGE_DIR,
        REPORT_STORAGE_DIR,
        LEARNING_STORAGE_DIR,
        RUNS_STORAGE_DIR,
        DB_STORAGE_DIR,
        EXPORT_STORAGE_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def portable_path(path: Path | str | None) -> str | None:
    """Persist project-relative paths instead of machine-specific absolute paths."""
    if path is None:
        return None
    raw = Path(path)
    # Prefer unresolved relative strings already under the project.
    if not raw.is_absolute():
        as_posix = raw.as_posix()
        if as_posix.startswith(("resume_engine/", "tests/", "docs/")):
            return as_posix
    resolved = raw.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return raw.as_posix()


def logical_artifact_id(jd_hash: str, run_id: str, stage: str, variant_id: str) -> str:
    """Stable cross-OS artifact ID: runs/<jd_hash>/<run_id>/<stage>/<variant>.json"""
    return f"runs/{jd_hash}/{run_id}/{stage}/{variant_id}.json"
