from pydantic import BaseModel, Field


class ResumeStrategy(BaseModel):
    strategy_id: str
    jd_hash: str
    positioning: dict[str, str]
    summary_focus: list[str] = Field(default_factory=list)
    experience_focus: list[str] = Field(default_factory=list)
    project_focus: list[str] = Field(default_factory=list)
    technical_skill_categories: dict[str, list[str]] = Field(default_factory=dict)
    certification_treatment: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_drift: list[str] = Field(default_factory=list)
    bullet_allocation: dict[str, int] = Field(default_factory=dict)
    placement_requirements: dict[str, list[str]] = Field(default_factory=dict)
    p4_limits: dict[str, float | int] = Field(default_factory=dict)


class VariantStrategy(BaseModel):
    variant_id: str
    positioning: str
    description: str
    emphasis: dict[str, float] = Field(default_factory=dict)
    bullet_bias: dict[str, float] = Field(default_factory=dict)
    rules: list[str] = Field(default_factory=list)
