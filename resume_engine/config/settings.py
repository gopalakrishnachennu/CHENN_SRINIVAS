import os
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
ONLINE_LEARNING_STORAGE_DIR = LEARNING_STORAGE_DIR / "online"
DB_STORAGE_DIR = STORAGE_DIR / "db"
DEFAULT_SQLITE_DB_PATH = DB_STORAGE_DIR / "resume_engine.sqlite3"
# Backward-compatible alias — prefer get_sqlite_db_path() at runtime.
SQLITE_DB_PATH = DEFAULT_SQLITE_DB_PATH
EXPORT_STORAGE_DIR = STORAGE_DIR / "exports"

DEFAULT_OPENAI_MODEL = "gpt-5.6"
DEFAULT_VARIANT_COUNT = 5
PROMPT_VERSION = "phase2_wave4_v1"


def load_local_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env.local")
    load_dotenv(PROJECT_ROOT / ".env")


def production_sqlite_db_path() -> Path:
    """Canonical production UI/engine SQLite path (never overridden by env)."""
    return DEFAULT_SQLITE_DB_PATH.resolve()


def get_sqlite_db_path() -> Path:
    """Runtime SQLite path. Honors RESUME_ENGINE_DB_PATH for test isolation."""
    override = (os.getenv("RESUME_ENGINE_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return production_sqlite_db_path()


def get_ui_artifact_dir(name: str = "ui") -> Path:
    """Runtime UI artifact root. Honors RESUME_ENGINE_UI_STORAGE."""
    override = (os.getenv("RESUME_ENGINE_UI_STORAGE") or "").strip()
    if override:
        root = Path(override).expanduser().resolve()
    else:
        root = (STORAGE_DIR / name).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def assert_db_path_not_production(*, context: str = "operation") -> Path:
    """Hard guard: refuse when pytest would hit the production DB."""
    path = get_sqlite_db_path().resolve()
    prod = production_sqlite_db_path()
    under_pytest = bool(
        os.getenv("PYTEST_CURRENT_TEST") or os.getenv("RESUME_ENGINE_FORCE_TEST_ISOLATION")
    )
    if under_pytest and path == prod:
        raise RuntimeError(
            "TEST_DATABASE_ISOLATION_VIOLATION: "
            f"{context} resolved DB path equals production SQLite ({prod})"
        )
    return path


def ensure_storage_dirs() -> None:
    for path in [
        BLUEPRINT_STORAGE_DIR,
        STRATEGY_STORAGE_DIR,
        GENERATED_STORAGE_DIR,
        VALIDATED_STORAGE_DIR,
        REJECTED_STORAGE_DIR,
        REPORT_STORAGE_DIR,
        LEARNING_STORAGE_DIR,
        ONLINE_LEARNING_STORAGE_DIR,
        RUNS_STORAGE_DIR,
        DB_STORAGE_DIR,
        EXPORT_STORAGE_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    get_sqlite_db_path().parent.mkdir(parents=True, exist_ok=True)


def portable_path(path: Path | str | None) -> str | None:
    """Persist project-relative paths instead of machine-specific absolute paths."""
    if path is None:
        return None
    raw = Path(path)
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
