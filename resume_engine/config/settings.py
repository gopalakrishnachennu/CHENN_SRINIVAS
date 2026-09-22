from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = PROJECT_ROOT / "resume_engine" / "storage"

BLUEPRINT_STORAGE_DIR = STORAGE_DIR / "blueprints"
STRATEGY_STORAGE_DIR = STORAGE_DIR / "strategies"
GENERATED_STORAGE_DIR = STORAGE_DIR / "generated"
VALIDATED_STORAGE_DIR = STORAGE_DIR / "validated"
REPORT_STORAGE_DIR = STORAGE_DIR / "reports"
LEARNING_STORAGE_DIR = STORAGE_DIR / "learning"

DEFAULT_OPENAI_MODEL = "gpt-5.6"
DEFAULT_VARIANT_COUNT = 5


def load_local_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env.local")
    load_dotenv(PROJECT_ROOT / ".env")


def ensure_storage_dirs() -> None:
    for path in [
        BLUEPRINT_STORAGE_DIR,
        STRATEGY_STORAGE_DIR,
        GENERATED_STORAGE_DIR,
        VALIDATED_STORAGE_DIR,
        REPORT_STORAGE_DIR,
        LEARNING_STORAGE_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
