from typing import Any

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    code: str
    severity: str
    message: str
    location: str | None = None
    repair_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidatorResult(BaseModel):
    name: str
    passed: bool
    score: float = 100.0
    issues: list[ValidationIssue] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationBundle(BaseModel):
    variant_id: str
    resume_id: str
    passed: bool
    optimization_score: float
    action: str
    subscores: dict[str, float] = Field(default_factory=dict)
    validator_results: list[ValidatorResult] = Field(default_factory=list)
    repair_plan: dict[str, Any] = Field(default_factory=dict)
