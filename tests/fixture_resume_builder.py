"""
fixture_resume_builder.py — build deterministic ResumeJSON objects for each
fixture. These represent 'good' resumes that should pass all validators,
allowing behavioral tests to verify each validator fires correctly.
"""
from __future__ import annotations

from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON


def _build_resume(
    blueprint: JDBlueprint,
    variant_id: str = "V01",
    extra_skills: dict[str, list[str]] | None = None,
    extra_bullets: list[str] | None = None,
) -> ResumeJSON:
    """
    Build a passing resume from the blueprint's P1/P2/P3 skills and
    responsibilities. Skills are arranged by priority, bullets use all
    P1+P2 terms, and summary mentions P1.
    """
    p1 = blueprint.priority_skills.get("P1", [])
    p2 = blueprint.priority_skills.get("P2", [])
    p3 = blueprint.priority_skills.get("P3", [])
    p4 = blueprint.priority_skills.get("P4", [])

    # Build summary covering all P1 skills
    p1_str = ", ".join(p1) if p1 else "cloud infrastructure"
    p2_str = ", ".join(p2[:4]) if p2 else "deployment automation"
    summary = (
        f"Senior engineer with deep expertise in {p1_str}. "
        f"Skilled in {p2_str} for high-performance production systems."
    )

    # Build technical skills grouped by priority
    skills: dict[str, list[str]] = {}
    if p1:
        skills["Core Technologies"] = list(p1)
    if p2:
        skills["Supporting Technologies"] = list(p2)
    if p3:
        skills["Additional Tools"] = list(p3)
    if p4:
        skills["Platform Utilities"] = list(p4)
    if extra_skills:
        for group, items in extra_skills.items():
            skills.setdefault(group, []).extend(items)

    # Build experience bullets covering P1 + P2 + responsibilities
    resp = blueprint.responsibilities
    core_bullet_1 = f"Led production deployments leveraging {', '.join(p1[:3])} for enterprise-scale workloads."
    core_bullet_2 = f"Automated workflows using {', '.join(p2[:3]) if p2 else 'CI/CD and Python'} across cloud infrastructure."
    resp_bullets = [f"Owned responsibility: {r}" for r in resp[:3]] if resp else []
    all_bullets = [core_bullet_1, core_bullet_2] + resp_bullets + (extra_bullets or [])

    # Second job covers remaining P1/P2 terms for coverage completeness
    p1_remaining = p1[3:] if len(p1) > 3 else []
    p2_remaining = p2[3:] if len(p2) > 3 else []
    combined_remaining = p1_remaining + p2_remaining
    second_bullet_1 = (
        f"Supported {', '.join(combined_remaining)} operations and platform reliability."
        if combined_remaining
        else "Supported cross-functional team operations and platform reliability."
    )
    second_bullet_2 = f"Delivered {blueprint.job.primary_family.replace('_', ' ')} improvements aligned with JD requirements."

    certifications = list(blueprint.certifications) if blueprint.certifications else []

    return ResumeJSON.model_validate({
        "target_title": blueprint.job.target_title or "Senior Engineer",
        "summary": summary,
        "technical_skills": skills,
        "experience": [
            {
                "company": "Company A",
                "title": blueprint.job.target_title or "Senior Engineer",
                "bullets": all_bullets,
            },
            {
                "company": "Company B",
                "title": f"{'Senior' if 'senior' in (blueprint.job.seniority or '') else ''} Engineer".strip(),
                "bullets": [second_bullet_1, second_bullet_2],
            },
        ],
        "projects": [],
        "certifications": certifications,
        "variant_id": variant_id,
        "source_blueprint_hash": blueprint.jd_hash,
    })


def good_resume_for(blueprint: JDBlueprint, variant_id: str = "V01") -> ResumeJSON:
    """Return a resume that should pass all validators for this blueprint."""
    return _build_resume(blueprint, variant_id=variant_id)


def bad_resume_missing_p1(blueprint: JDBlueprint) -> ResumeJSON:
    """Resume missing all P1 skills — should fail coverage validator."""
    p2 = blueprint.priority_skills.get("P2", [])
    p3 = blueprint.priority_skills.get("P3", [])
    return ResumeJSON.model_validate({
        "target_title": blueprint.job.target_title or "Senior Engineer",
        "summary": "Engineer with cloud experience.",
        "technical_skills": {
            "Tools": (p2[:2] if p2 else []) + (p3[:1] if p3 else []),
        },
        "experience": [
            {
                "company": "Company A",
                "title": "Engineer",
                "bullets": [
                    "Worked on various technical projects.",
                    "Supported team operations.",
                ],
            }
        ],
        "projects": [],
        "certifications": [],
        "variant_id": "VBAD_P1",
        "source_blueprint_hash": blueprint.jd_hash,
    })


def bad_resume_with_hallucination(blueprint: JDBlueprint) -> ResumeJSON:
    """Resume that adds an unauthorized technology — should fail firewall."""
    resume = good_resume_for(blueprint, variant_id="VBAD_HALL")
    resume.technical_skills.setdefault("CRM Tools", []).append("Salesforce")
    resume.summary += " Salesforce CRM platform."
    return resume


def bad_resume_with_duplicates(blueprint: JDBlueprint) -> ResumeJSON:
    """Resume with duplicate bullets — should fail duplicate validator."""
    p1 = blueprint.priority_skills.get("P1", ["Python"])
    dupe_bullet = f"Deployed {p1[0]} workloads to production cloud infrastructure."
    return ResumeJSON.model_validate({
        "target_title": blueprint.job.target_title or "Senior Engineer",
        "summary": f"Engineer with {', '.join(p1)} expertise.",
        "technical_skills": {"Core": list(p1)},
        "experience": [
            {
                "company": "Company A",
                "title": "Engineer",
                "bullets": [dupe_bullet, dupe_bullet],  # exact duplicate
            }
        ],
        "projects": [],
        "certifications": [],
        "variant_id": "VBAD_DUPE",
        "source_blueprint_hash": blueprint.jd_hash,
    })


def bad_resume_missing_ai_tools(blueprint: JDBlueprint) -> ResumeJSON:
    """Resume missing AI tool placements for P1 AND P2 AI tools.

    Omits all AI tools from technical_skills and experience bullets so that
    the AI placement validator fires on any fixture that has AI tools at P1 or P2.
    """
    ai_hints = {"openai", "claude", "anthropic", "langchain", "langgraph", "bedrock", "vertex", "mosaic"}
    p1_ai = [s for s in blueprint.priority_skills.get("P1", []) if any(h in s.lower() for h in ai_hints)]
    p2_ai = [s for s in blueprint.priority_skills.get("P2", []) if any(h in s.lower() for h in ai_hints)]
    all_ai = set(p1_ai + p2_ai)

    if not all_ai:
        return good_resume_for(blueprint, variant_id="VBAD_AI")

    # Build a resume with non-AI skills only — no AI tools anywhere
    p1_non = [s for s in blueprint.priority_skills.get("P1", []) if s not in all_ai]
    p2_non = [s for s in blueprint.priority_skills.get("P2", []) if s not in all_ai]
    summary_skills = p1_non[:3] if p1_non else p2_non[:3] if p2_non else ["Python"]
    return ResumeJSON.model_validate({
        "target_title": blueprint.job.target_title or "Senior Engineer",
        "summary": f"Engineer with expertise in {', '.join(summary_skills)} and cloud platforms.",
        "technical_skills": {
            "Cloud": p1_non[:4] if p1_non else ["Python"],
            "DevOps": p2_non[:3] if p2_non else [],
        },
        "experience": [
            {
                "company": "Company A",
                "title": "Engineer",
                "bullets": [
                    "Built cloud infrastructure and automated deployments.",
                    "Managed production platform operations.",
                ],
            }
        ],
        "projects": [],
        "certifications": [],
        "variant_id": "VBAD_AI",
        "source_blueprint_hash": blueprint.jd_hash,
    })


def bad_resume_wrong_family(blueprint: JDBlueprint) -> ResumeJSON:
    """Resume with unrelated Salesforce/frontend positioning — should fail hybrid validator."""
    resume = good_resume_for(blueprint, variant_id="VBAD_FAM")
    resume.technical_skills["CRM"] = ["Salesforce", "Salesforce Administrator"]
    resume.summary = "Salesforce Administrator with CRM experience. " + resume.summary
    return resume
