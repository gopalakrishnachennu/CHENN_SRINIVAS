from typing import Any, Optional

from pydantic import BaseModel, Field


class BlueprintJob(BaseModel):
    target_title: Optional[str] = None
    company: Optional[str] = None
    primary_family: str
    primary_confidence: Optional[float] = None
    secondary_family: str = "none"
    seniority: str
    seniority_confidence: Optional[float] = None
    hybrid_probability: float = 0.0


class BlueprintEntity(BaseModel):
    name: str
    category: str
    priority: str
    source: str
    requirement: Optional[str] = None
    evidence: Optional[str] = None
    confidence: Optional[float] = None
    placement: list[str] = Field(default_factory=list)
    parent_skill: Optional[str] = None


class GenerationContract(BaseModel):
    allowed_technologies: list[str] = Field(default_factory=list)
    allow_new_llm_skills: bool = False
    allowed_sources: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class QualityGates(BaseModel):
    P1_coverage_min: float = 1.0
    P2_coverage_min: float = 0.9
    unapproved_skill_count_max: int = 0
    duplicate_bullet_count_max: int = 0
    role_drift_allowed: bool = False
    technology_drift_allowed: bool = False


class JDBlueprint(BaseModel):
    blueprint_version: str
    jd_hash: str
    created_at: str
    job: BlueprintJob
    priority_skills: dict[str, list[str]] = Field(default_factory=dict)
    entities: list[BlueprintEntity] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    domain_terms: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    generation_contract: GenerationContract
    quality_gates: QualityGates = Field(default_factory=QualityGates)

    @classmethod
    def from_json_file(cls, path: str):
        import json

        with open(path, "r", encoding="utf-8") as f:
            return cls.model_validate(json.load(f))

    def as_prompt_payload(self) -> dict[str, Any]:
        return self.model_dump()
