"""Seed a realistic family-covered job library for UI/workflow testing.

The seed is curated, non-scraped, and non-destructive. It creates at least five
real-world style jobs per active family so filters, Laya classification, match
flows, salary/auth parsing, and resume creation can be tested with meaningful
data instead of toy records.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resume_engine.ui.services import job_service
from resume_engine.ui.services.family_registry_service import list_families

FAMILY_ROLES: dict[str, list[tuple[str, str, str, str, str]]] = {
    "ai_ml": [
        ("OpenAI", "Machine Learning Engineer, Applied AI", "San Francisco, CA", "$180K-$240K annually", "https://openai.com/careers"),
        ("NVIDIA", "Senior AI Infrastructure Engineer", "Santa Clara, CA", "$170K-$230K annually", "https://www.nvidia.com/en-us/about-nvidia/careers/"),
        ("Google", "Generative AI Engineer", "New York, NY", "$155K-$220K annually", "https://www.google.com/about/careers/"),
        ("Meta", "Applied Machine Learning Scientist", "Menlo Park, CA", "$160K-$235K annually", "https://www.metacareers.com/jobs/"),
        ("Microsoft", "Principal AI Engineer", "Redmond, WA", "$165K-$225K annually", "https://careers.microsoft.com/"),
    ],
    "data_engineering": [
        ("Netflix", "Senior Data Engineer, Streaming Analytics", "Los Gatos, CA", "$150K-$210K annually", "https://jobs.netflix.com/"),
        ("Databricks", "Data Platform Engineer", "San Francisco, CA", "$145K-$200K annually", "https://www.databricks.com/company/careers"),
        ("Snowflake", "ETL Data Engineer", "Bellevue, WA", "$135K-$185K annually", "https://careers.snowflake.com/"),
        ("Walmart Global Tech", "Staff Data Engineer", "Bentonville, AR", "$130K-$180K annually", "https://careers.walmart.com/"),
        ("Capital One", "Lead Data Pipeline Engineer", "McLean, VA", "$140K-$195K annually", "https://www.capitalonecareers.com/"),
    ],
    "data_analytics": [
        ("Airbnb", "Senior Data Analyst, Marketplace", "San Francisco, CA", "$125K-$170K annually", "https://careers.airbnb.com/"),
        ("Uber", "Business Intelligence Analyst", "Chicago, IL", "$105K-$150K annually", "https://www.uber.com/us/en/careers/"),
        ("LinkedIn", "Product Analytics Manager", "Sunnyvale, CA", "$145K-$205K annually", "https://careers.linkedin.com/"),
        ("DoorDash", "Analytics Engineer", "Remote within the United States", "$120K-$165K annually", "https://careers.doordash.com/"),
        ("Target", "Data Analyst, Digital", "Minneapolis, MN", "$95K-$135K annually", "https://jobs.target.com/"),
    ],
    "devops_cloud": [
        ("Amazon Web Services", "Cloud DevOps Engineer", "Seattle, WA", "$135K-$190K annually", "https://www.amazon.jobs/"),
        ("HashiCorp", "Senior Terraform Platform Engineer", "Remote within the United States", "$140K-$195K annually", "https://www.hashicorp.com/careers"),
        ("GitLab", "Site Reliability Engineer", "Remote within the United States", "$130K-$185K annually", "https://about.gitlab.com/jobs/"),
        ("Red Hat", "Kubernetes Platform Engineer", "Raleigh, NC", "$120K-$165K annually", "https://www.redhat.com/en/jobs"),
        ("Cloudflare", "Infrastructure Automation Engineer", "Austin, TX", "$125K-$175K annually", "https://www.cloudflare.com/careers/"),
    ],
    "software_engineering": [
        ("Microsoft", "Principal Software Engineer - FullStack", "Noida, Uttar Pradesh", "INR 45L-INR 60L annually", "https://careers.microsoft.com/"),
        ("Stripe", "Backend Software Engineer", "New York, NY", "$145K-$205K annually", "https://stripe.com/jobs"),
        ("Atlassian", "Senior Full Stack Engineer", "Remote within the United States", "$135K-$190K annually", "https://www.atlassian.com/company/careers"),
        ("Adobe", "Software Development Engineer", "San Jose, CA", "$130K-$180K annually", "https://careers.adobe.com/"),
        ("Shopify", "Staff Backend Engineer", "Remote within Canada", "CAD 140K-CAD 190K annually", "https://www.shopify.com/careers"),
    ],
    "test_engineering": [
        ("Apple", "SDET, Quality Engineering", "Cupertino, CA", "$130K-$180K annually", "https://jobs.apple.com/"),
        ("Tesla", "Test Automation Engineer", "Austin, TX", "$105K-$150K annually", "https://www.tesla.com/careers"),
        ("ServiceNow", "Senior QA Automation Engineer", "Santa Clara, CA", "$120K-$165K annually", "https://careers.servicenow.com/"),
        ("Roku", "Software QA Engineer", "San Jose, CA", "$110K-$155K annually", "https://www.weareroku.com/jobs"),
        ("Intuit", "Quality Engineer, Payments", "Mountain View, CA", "$120K-$170K annually", "https://www.intuit.com/careers/"),
    ],
    "infrastructure_support": [
        ("Cisco", "Network Support Engineer", "San Jose, CA", "$95K-$135K annually", "https://jobs.cisco.com/"),
        ("Dell Technologies", "Systems Administrator", "Round Rock, TX", "$85K-$120K annually", "https://jobs.dell.com/"),
        ("HP", "IT Support Engineer", "Palo Alto, CA", "$80K-$115K annually", "https://jobs.hp.com/"),
        ("Oracle", "Linux Systems Engineer", "Austin, TX", "$100K-$145K annually", "https://www.oracle.com/careers/"),
        ("Verizon", "Enterprise Network Operations Engineer", "Basking Ridge, NJ", "$95K-$135K annually", "https://www.verizon.com/about/careers"),
    ],
    "cybersecurity": [
        ("CrowdStrike", "Cybersecurity Engineer", "Remote within the United States", "$130K-$185K annually", "https://www.crowdstrike.com/careers/"),
        ("Palo Alto Networks", "Cloud Security Engineer", "Santa Clara, CA", "$140K-$200K annually", "https://jobs.paloaltonetworks.com/"),
        ("Okta", "Application Security Engineer", "San Francisco, CA", "$135K-$190K annually", "https://www.okta.com/company/careers/"),
        ("Mandiant", "Security Operations Consultant", "Reston, VA", "$120K-$170K annually", "https://www.mandiant.com/careers"),
        ("JPMorgan Chase", "Information Security Analyst", "Plano, TX", "$105K-$150K annually", "https://careers.jpmorgan.com/"),
    ],
    "salesforce": [
        ("Salesforce", "Salesforce Developer", "San Francisco, CA", "$130K-$185K annually", "https://www.salesforce.com/company/careers/"),
        ("Deloitte", "Salesforce Technical Consultant", "New York, NY", "$115K-$165K annually", "https://www2.deloitte.com/us/en/careers/careers.html"),
        ("Accenture", "Salesforce Apex Engineer", "Chicago, IL", "$105K-$155K annually", "https://www.accenture.com/us-en/careers"),
        ("Slalom", "Salesforce Solution Architect", "Seattle, WA", "$135K-$190K annually", "https://www.slalom.com/careers"),
        ("PwC", "Salesforce CRM Developer", "Dallas, TX", "$110K-$160K annually", "https://www.pwc.com/us/en/careers.html"),
    ],
    "finance_analytics": [
        ("Goldman Sachs", "Finance Analytics Associate", "New York, NY", "$115K-$165K annually", "https://www.goldmansachs.com/careers/"),
        ("American Express", "FP&A Analytics Manager", "Phoenix, AZ", "$110K-$155K annually", "https://www.americanexpress.com/en-us/careers/"),
        ("Visa", "Financial Data Analyst", "Foster City, CA", "$120K-$170K annually", "https://usa.visa.com/careers.html"),
        ("Bloomberg", "Revenue Forecasting Analyst", "New York, NY", "$105K-$150K annually", "https://www.bloomberg.com/company/careers/"),
        ("PayPal", "Finance Business Intelligence Analyst", "San Jose, CA", "$110K-$155K annually", "https://www.paypal.com/us/webapps/mpp/jobs"),
    ],
    "marketing_analytics": [
        ("HubSpot", "Marketing Analytics Manager", "Boston, MA", "$115K-$160K annually", "https://www.hubspot.com/careers"),
        ("Google", "Growth Analytics Lead", "Mountain View, CA", "$145K-$205K annually", "https://www.google.com/about/careers/"),
        ("Nike", "Digital Marketing Analyst", "Beaverton, OR", "$95K-$135K annually", "https://jobs.nike.com/"),
        ("Spotify", "Campaign Analytics Specialist", "New York, NY", "$105K-$150K annually", "https://www.lifeatspotify.com/jobs"),
        ("Pinterest", "Performance Marketing Analyst", "San Francisco, CA", "$120K-$170K annually", "https://www.pinterestcareers.com/"),
    ],
    "manufacturing_test": [
        ("Intel", "Manufacturing Test Engineer", "Hillsboro, OR", "$105K-$150K annually", "https://jobs.intel.com/"),
        ("Applied Materials", "Hardware Test Engineer", "Santa Clara, CA", "$110K-$155K annually", "https://www.appliedmaterials.com/us/en/careers.html"),
        ("Texas Instruments", "ATE Validation Engineer", "Dallas, TX", "$95K-$140K annually", "https://careers.ti.com/"),
        ("Northrop Grumman", "Manufacturing Test Systems Engineer", "Redondo Beach, CA", "$115K-$165K annually", "https://www.northropgrumman.com/jobs/"),
        ("Lam Research", "Product Test Engineer", "Fremont, CA", "$105K-$150K annually", "https://www.lamresearch.com/careers/"),
    ],
}


FAMILY_KEYWORDS = {
    "ai_ml": "machine learning, AI, model evaluation, Python, PyTorch, LLM systems",
    "data_engineering": "data engineering, ETL, Spark, SQL, pipeline orchestration, data platform",
    "data_analytics": "data analytics, BI dashboards, metrics, Tableau, Power BI, stakeholder reporting",
    "devops_cloud": "DevOps, cloud, Kubernetes, Terraform, CI/CD, site reliability engineering",
    "software_engineering": "software engineering, backend services, full stack, architecture, code quality",
    "test_engineering": "SDET, QA, test automation, regression testing, release validation",
    "infrastructure_support": "systems administrator, IT support, network support, Linux, endpoint operations",
    "cybersecurity": "cybersecurity, vulnerability management, security operations, incident response",
    "salesforce": "Salesforce, Apex, LWC, CRM, flows, integrations",
    "finance_analytics": "finance analytics, FP&A, forecasting, variance analysis, financial modeling",
    "marketing_analytics": "marketing analytics, campaign analytics, attribution, SEO, growth metrics",
    "manufacturing_test": "manufacturing test, hardware test, ATE, validation engineering, test fixtures",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _jd_text(family_id: str, company: str, title: str, location: str, salary: str) -> str:
    keywords = FAMILY_KEYWORDS[family_id]
    work_mode = "Remote within the United States." if "Remote" in location else "Hybrid, three days in office."
    return f"""
{title}
{company}
Location: {location}
{work_mode}
Full-time W2 role.
Salary: {salary}.
Must be authorized to work in the United States. We cannot provide sponsorship now or in the future.
Minimum qualifications include 5+ years of experience in {keywords}.
Responsibilities include delivery ownership, production quality, cross-functional collaboration, documentation, and measurable business outcomes.
Preferred qualifications include cloud experience, agile delivery, communication with stakeholders, and comfort supporting application workflows.
Technologies and domain signals: {keywords}.
"""


def iter_seed_jobs():
    for family_id, rows in FAMILY_ROLES.items():
        for company, title, location, salary, url in rows:
            yield {
                "family_id": family_id,
                "company": company,
                "title": title,
                "location": location,
                "salary": salary,
                "job_url": f"{url.rstrip('/')}/#{_slug(title)}",
                "jd_text": _jd_text(family_id, company, title, location, salary),
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    active_families = {f["family_id"] for f in list_families()}
    jobs = [job for job in iter_seed_jobs() if job["family_id"] in active_families]
    if args.limit:
        jobs = jobs[: args.limit]

    expected = Counter(job["family_id"] for job in jobs)
    missing = sorted(f for f in active_families if expected[f] < 5)
    if missing and not args.limit:
        raise SystemExit(f"Seed coverage below 5 for: {', '.join(missing)}")

    created = 0
    existing = 0
    for job in jobs:
        if args.dry_run:
            print(f"{job['family_id']}: {job['company']} - {job['title']}")
            continue
        before = job_service.find_duplicate_job(jd_text=job["jd_text"], job_url=job["job_url"])
        saved = job_service.create_draft(
            job["jd_text"],
            title=job["title"],
            company=job["company"],
            location=job["location"],
            job_url=job["job_url"],
            source="curated_family_seed",
            actor="seed_family_job_library",
        )
        if before:
            existing += 1
        else:
            created += 1
        print(f"{saved['primary_family'] or 'unknown'}: {saved['company']} - {saved['title']}")

    print(f"seed_jobs={len(jobs)} created={created} existing={existing} dry_run={args.dry_run}")
    for family_id, count in sorted(expected.items()):
        print(f"{family_id}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
