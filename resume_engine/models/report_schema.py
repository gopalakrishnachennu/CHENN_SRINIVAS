from pydantic import BaseModel, Field


class ImplementationModuleStatus(BaseModel):
    implemented: bool
    tested: bool = False
    details: str = ""


class ImplementationAudit(BaseModel):
    phase: str = "Phase 2"
    modules: dict[str, ImplementationModuleStatus] = Field(default_factory=dict)
    implemented_count: int = 0
    total_count: int = 0
    implementation_percent: float = 0.0
