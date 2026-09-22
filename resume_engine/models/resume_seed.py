from pydantic import BaseModel, Field


class SeedCompany(BaseModel):
    company: str
    title_style: str = "JD-aligned"
    experience_order: int


class ResumeSeed(BaseModel):
    companies: list[SeedCompany] = Field(default_factory=list)
    template_notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_json_file(cls, path: str):
        import json

        with open(path, "r", encoding="utf-8") as f:
            return cls.model_validate(json.load(f))
