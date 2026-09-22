from pathlib import Path

from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.validation_schema import ValidationBundle
from resume_engine.reports.resume_validation_report import (
    save_resume_validation_json,
    save_resume_validation_text,
)


def save_validation_reports(blueprint: JDBlueprint, bundle: ValidationBundle) -> tuple[Path, Path]:
    json_path = save_resume_validation_json(bundle)
    text_path = save_resume_validation_text(blueprint, bundle)
    return json_path, text_path
