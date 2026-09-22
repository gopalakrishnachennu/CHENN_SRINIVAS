from pydantic import BaseModel, Field


class ImplementationModuleStatus(BaseModel):
    implemented: bool
    tested: bool = False
    details: str = ""
    exists: bool = False
    imports_successfully: bool = False
    unit_test_exists: bool = False
    unit_test_passed: bool | None = None
    integration_test_exists: bool = False
    integration_test_passed: bool | None = None
    live_test_status: str = "LIVE_TEST_NOT_RUN"


class ImplementationAudit(BaseModel):
    phase: str = "Phase 2.6"
    modules: dict[str, ImplementationModuleStatus] = Field(default_factory=dict)
    implemented_count: int = 0
    total_count: int = 0
    implementation_percent: float = 0.0
