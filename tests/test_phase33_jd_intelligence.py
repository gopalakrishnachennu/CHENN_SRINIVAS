from __future__ import annotations

from resume_engine.jd_intelligence.education_parser import parse_education
from resume_engine.jd_intelligence.employment_parser import parse_employment
from resume_engine.jd_intelligence.experience_parser import parse_experience
from resume_engine.jd_intelligence.job_analyzer import analyze_text, filter_columns
from resume_engine.jd_intelligence.location_parser import parse_location
from resume_engine.jd_intelligence.salary_parser import parse_salary
from resume_engine.jd_intelligence.schema import raw_value
from resume_engine.jd_intelligence.work_auth_parser import parse_work_auth
from resume_engine.jd_intelligence.work_mode_parser import (
    parse_relocation,
    parse_travel,
    parse_work_mode,
)


def test_city_state_location():
    result = parse_location("Role is based in Austin, TX.")
    assert raw_value(result["city"]) == "Austin"
    assert raw_value(result["state"]) == "Texas"
    assert raw_value(result["country"]) == "United States"


def test_multiple_locations():
    result = parse_location("Locations: San Bruno, CA and Bentonville, AR.")
    locations = result["multiple_locations"]
    assert len(locations) == 2
    assert {item["city"] for item in locations} == {"San Bruno", "Bentonville"}


def test_india_city_state_location():
    result = parse_location("Location: Noida, Uttar Pradesh")
    assert raw_value(result["city"]) == "Noida"
    assert raw_value(result["state"]) == "Uttar Pradesh"
    assert raw_value(result["country"]) == "India"
    assert result["country_code"] == "IN"


def test_new_mexico_is_us_state_not_country():
    result = parse_location("Location: New Mexico")
    assert raw_value(result["city"]) is None
    assert raw_value(result["state"]) == "New Mexico"
    assert raw_value(result["country"]) == "United States"
    assert result["country_code"] == "US"
    assert result["location_needs_review"] is False


def test_single_city_requires_review_without_state_or_country():
    result = parse_location("Location: Noida")
    assert raw_value(result["city"]) == "Noida"
    assert raw_value(result["state"]) is None
    assert raw_value(result["country"]) is None
    assert result["city"]["status"] == "AMBIGUOUS"
    assert result["location_needs_review"] is True


def test_single_unknown_city_needs_human_review():
    result = parse_location("Location: Springfield")
    assert raw_value(result["city"]) == "Springfield"
    assert raw_value(result["state"]) is None
    assert raw_value(result["country"]) is None
    assert result["city"]["status"] == "AMBIGUOUS"
    assert result["location_needs_review"] is True


def test_work_authorization_country_is_not_job_location():
    result = parse_location("Must be authorized to work in the United States.")
    assert raw_value(result["city"]) is None
    assert raw_value(result["state"]) is None
    assert raw_value(result["country"]) is None


def test_does_not_infer_company_hq():
    result = parse_location("Join Walmart as a Data Engineer. Build data pipelines.")
    assert raw_value(result["city"]) is None
    assert raw_value(result["state"]) is None


def test_remote_us_only_and_hybrid_days():
    remote = parse_work_mode("This role is remote within the continental United States.")
    assert raw_value(remote["work_mode"]) == "REMOTE"
    assert raw_value(remote["remote_scope"]) == "US_ONLY"
    hybrid = parse_work_mode("Hybrid, three days in office.")
    assert raw_value(hybrid["work_mode"]) == "HYBRID"
    assert hybrid["hybrid_days_per_week"] == 3


def test_employment_and_engagement_types():
    assert raw_value(parse_employment("Full-time W2 role.")["employment_type"]) == "FULL_TIME"
    assert raw_value(parse_employment("Full-time W2 role.")["engagement_type"]) == "W2"
    assert raw_value(parse_employment("6 month contract C2C accepted.")["employment_type"]) == "CONTRACT"
    assert raw_value(parse_employment("6 month contract C2C accepted.")["engagement_type"]) == "C2C"
    assert parse_employment("6 month contract C2C accepted.")["contract_duration_value"] == 6
    assert raw_value(parse_employment("Contract-to-hire role.")["engagement_type"]) == "C2H"
    assert raw_value(parse_employment("1099 consultant.")["engagement_type"]) == "1099"


def test_travel_and_relocation():
    travel = parse_travel("Up to 25% travel required.")
    assert travel["travel_required"] is True
    assert travel["travel_percentage_max"] == 25
    assert parse_travel("No special requirements.")["travel_required"] is None
    assert raw_value(parse_relocation("Relocation assistance offered.")["relocation_status"]) == "OFFERED"
    assert raw_value(parse_relocation("Relocation required.")["relocation_status"]) == "REQUIRED"
    assert raw_value(parse_relocation("No relocation text.")["relocation_status"]) == "NOT_STATED"


def test_salary_formats():
    annual = parse_salary("Salary: $120K-$150K annually")
    assert annual["salary_min"] == 120000
    assert annual["salary_max"] == 150000
    assert annual["salary_currency"] == "USD"
    assert annual["salary_period"] == "ANNUAL"
    hourly = parse_salary("$65-$75/hour")
    assert hourly["salary_min"] == 65
    assert hourly["salary_max"] == 75
    assert hourly["salary_period"] == "HOURLY"
    inr = parse_salary("Compensation ₹20L-₹30L")
    assert inr["salary_currency"] == "INR"
    assert inr["salary_min"] == 2_000_000
    assert raw_value(parse_salary("Competitive pay.")["salary_status"]) == "NOT_STATED"


def test_work_authorization_no_sponsorship_not_equal_gc_citizen():
    result = parse_work_auth("We cannot provide sponsorship now or in the future.")
    assert raw_value(result["sponsorship_status"]) == "NO_SPONSORSHIP"
    assert raw_value(result["authorization_requirement"]) == "NONE_STATED"


def test_work_authorization_statuses():
    assert raw_value(parse_work_auth("US Citizen only.")["authorization_requirement"]) == "US_CITIZEN_ONLY"
    assert raw_value(parse_work_auth("Must be authorized to work in the United States.")["authorization_requirement"]) == "AUTHORIZED_TO_WORK_US"
    assert raw_value(parse_work_auth("H1B transfer supported.")["h1b_status"]) == "TRANSFER_ONLY"
    assert raw_value(parse_work_auth("OPT and CPT accepted.")["student_visa_status"]) == "OPT_CPT_ALLOWED"
    assert raw_value(parse_work_auth("EAD accepted.")["ead_status"]) == "ACCEPTED"


def test_experience_and_education_separated_from_skills():
    exp = parse_experience("8+ years software engineering experience required.")
    assert raw_value(exp["minimum_years_experience"]) == 8
    assert exp["required_experience"] == ["software engineering experience required"]
    edu = parse_education("Bachelor's degree in Computer Science or equivalent experience.")
    assert edu["required_degree_levels"] == ["BACHELOR"]
    assert edu["required_majors"] == ["Computer Science"]
    assert edu["equivalent_experience_accepted"] is True


def test_complete_end_to_end_jd_intelligence():
    jd = """
    Senior Machine Learning Engineer
    Austin, TX
    Hybrid, three days in office
    Full-time
    Salary: $150,000-$190,000 annually.
    Must be authorized to work in the United States.
    We cannot provide sponsorship now or in the future.
    8+ years software engineering.
    Bachelor's degree in Computer Science or equivalent experience.
    Python, PyTorch, AWS.
    Up to 10% travel.
    """
    intel = analyze_text(jd, company="Acme", location="Austin, TX", job_url="https://example.test/job", title="Senior Machine Learning Engineer")
    columns = filter_columns(intel)
    assert columns["city"] == "Austin"
    assert columns["state"] == "Texas"
    assert columns["work_mode"] == "HYBRID"
    assert columns["employment_type"] == "FULL_TIME"
    assert columns["salary_min"] == 150000
    assert columns["salary_max"] == 190000
    assert columns["authorization_requirement"] == "AUTHORIZED_TO_WORK_US"
    assert columns["sponsorship_status"] == "NO_SPONSORSHIP"
    assert columns["minimum_years_experience"] == 8
    assert intel["laya_workflow_review"]["schema_version"] == "laya-workflow-review-v1"
    assert intel["laya_workflow_review"]["ready_for_matching"] is True
    assert any(
        item["key"] == "role_drift_guard"
        for item in intel["laya_workflow_review"]["decisions"]
    )


def test_absence_end_to_end_jd_intelligence():
    columns = filter_columns(analyze_text("Data Engineer\nPython\nSQL\nBuild data pipelines"))
    assert columns["city"] is None
    assert columns["work_mode"] == "UNKNOWN"
    assert columns["employment_type"] == "UNKNOWN"
    assert columns["salary_min"] is None
    assert columns["sponsorship_status"] == "SPONSORSHIP_NOT_STATED"
    assert columns["authorization_requirement"] == "NONE_STATED"


def test_laya_workflow_review_blocks_missing_required_intake():
    intel = analyze_text("AI engineer", title="AI Engineer")
    review = intel["laya_workflow_review"]
    assert review["readiness"] == "BLOCKED"
    assert review["ready_for_resume"] is False
    assert any(item["key"] == "jd_intake_completeness" for item in review["human_review_queue"])
