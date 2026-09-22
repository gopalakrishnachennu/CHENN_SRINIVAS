import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


RequirementLevel = Literal[
    "mandatory",
    "required",
    "preferred",
    "mentioned",
]

EntityCategory = Literal[
    "programming_language",
    "framework",
    "ai_tool",
    "ai_framework",
    "cloud",
    "data_platform",
    "database",
    "devops",
    "observability",
    "testing",
    "bi_analytics",
    "security",
    "methodology",
    "certification",
    "business_skill",
    "other",
]


class JDEntity(BaseModel):
    name: str
    category: EntityCategory
    requirement: RequirementLevel
    evidence: str


class JDExtraction(BaseModel):
    target_title: Optional[str] = None
    company_name: Optional[str] = None
    seniority_signals: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    entities: list[JDEntity] = Field(default_factory=list)
    domain_terms: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


DATA_DIR = Path("resume_engine_data")
BLUEPRINT_DIR = DATA_DIR / "blueprints"
REGISTRY_FILE = DATA_DIR / "skill_registry.json"
HISTORY_FILE = DATA_DIR / "jd_history.jsonl"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")

SEED_REGISTRY = {
    "databricks": {
        "canonical": "Databricks",
        "category": "data_platform",
        "adjacent": ["Apache Spark", "PySpark", "Delta Lake", "Unity Catalog"],
        "seen": 0,
    },
    "apache spark": {
        "canonical": "Apache Spark",
        "category": "data_platform",
        "adjacent": ["PySpark", "Databricks", "Delta Lake"],
        "seen": 0,
    },
    "airflow": {
        "canonical": "Apache Airflow",
        "category": "data_platform",
        "adjacent": ["DAGs", "Python", "Data Orchestration"],
        "seen": 0,
    },
    "openai": {
        "canonical": "OpenAI",
        "category": "ai_tool",
        "adjacent": ["OpenAI API", "Prompt Engineering", "Embeddings", "RAG"],
        "seen": 0,
    },
    "openai api": {
        "canonical": "OpenAI API",
        "category": "ai_tool",
        "adjacent": ["Prompt Engineering", "Embeddings", "RAG", "Tool Calling"],
        "seen": 0,
    },
    "claude": {
        "canonical": "Claude",
        "category": "ai_tool",
        "adjacent": ["Anthropic API", "Prompt Engineering", "Tool Use"],
        "seen": 0,
    },
    "anthropic": {
        "canonical": "Anthropic",
        "category": "ai_tool",
        "adjacent": ["Claude", "Anthropic API"],
        "seen": 0,
    },
    "kubernetes": {
        "canonical": "Kubernetes",
        "category": "devops",
        "adjacent": ["Docker", "Helm", "Terraform", "CI/CD"],
        "seen": 0,
    },
    "terraform": {
        "canonical": "Terraform",
        "category": "devops",
        "adjacent": ["Infrastructure as Code", "AWS", "Azure", "Kubernetes"],
        "seen": 0,
    },
    "snowflake": {
        "canonical": "Snowflake",
        "category": "data_platform",
        "adjacent": ["SQL", "dbt", "Data Warehousing"],
        "seen": 0,
    },
    "langchain": {
        "canonical": "LangChain",
        "category": "ai_framework",
        "adjacent": ["RAG", "Embeddings", "Vector Databases", "LLM Applications"],
        "seen": 0,
    },
}

FAMILY_CRITERIA = {
    "data_engineering": "ETL, pipelines, Spark, Databricks, databases, warehouses, data platforms",
    "data_analytics": "SQL analysis, BI, dashboards, reporting, analytics and insights",
    "ai_ml": "machine learning, AI engineering, LLMs, models, RAG and generative AI",
    "devops_cloud": "CI/CD, infrastructure, Kubernetes, Terraform, cloud operations and automation",
    "software_engineering": "application development, backend, APIs, services and software engineering",
    "infrastructure_support": "systems, networking, technical support, servers, data centers and infrastructure",
    "test_engineering": "testing, validation, test automation, manufacturing testing and quality",
    "other": "work that does not strongly fit the other technical families",
}

EXPLICIT_PRIORITY = {
    "mandatory": "P1",
    "required": "P2",
    "preferred": "P3",
}

FAMILY_SIGNAL_TERMS = {
    "devops_cloud": {
        "aws",
        "azure",
        "gcp",
        "terraform",
        "kubernetes",
        "ci/cd",
        "docker",
        "helm",
        "infrastructure",
        "deployment",
        "deployments",
        "cloud",
    },
    "data_engineering": {
        "databricks",
        "spark",
        "apache spark",
        "pyspark",
        "delta lake",
        "etl",
        "pipeline",
        "pipelines",
        "data platform",
        "workloads",
    },
    "ai_ml": {
        "openai",
        "openai api",
        "claude",
        "claude api",
        "langchain",
        "langgraph",
        "rag",
        "embeddings",
        "generative ai",
        "llm",
    },
}


def ensure_project_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    BLUEPRINT_DIR.mkdir(exist_ok=True)


def load_environment() -> None:
    load_dotenv(".env.local")
    load_dotenv()

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key or key == "PASTE_YOUR_OPENAI_KEY_HERE":
        os.environ["OPENAI_API_KEY"] = getpass("Enter OpenAI API Key: ")

    global OPENAI_MODEL
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", OPENAI_MODEL)


def load_laya_agent():
    import laya

    print("Loading Laya...")
    agent = laya.load("convaiinnovations/laya")
    print("Laya loaded.")
    return agent


def extract_jd(jd_text: str, client: OpenAI) -> JDExtraction:
    system_prompt = """
You are the deterministic extraction layer of a resume optimization system.

Your job is ONLY to extract information explicitly present in the supplied
job description.

STRICT RULES:

1. Do NOT invent adjacent technologies.
2. Do NOT recommend technologies.
3. Do NOT add skills simply because they commonly belong to the role.
4. Capture ALL explicitly mentioned technologies, tools, AI products,
   platforms, frameworks, databases, cloud services and certifications.
5. Preserve important named products such as:
   OpenAI, Claude, Anthropic, MCP, LangChain, LangGraph, Databricks,
   Snowflake, AWS, Azure, Kubernetes, Terraform, etc.
6. Extract meaningful responsibilities separately.
7. Determine requirement level from JD wording:

   mandatory:
       must have, mandatory, essential, required certification,
       minimum requirement

   required:
       required experience, should have, needs experience,
       expected proficiency

   preferred:
       preferred, nice to have, plus, desirable

   mentioned:
       technology appears in the JD but no clear requirement level exists

8. Do not create inferred or adjacent skills.
9. Do not write a resume.
10. Return only the requested structured information.
"""

    response = client.responses.parse(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": jd_text},
        ],
        text_format=JDExtraction,
    )

    if response.output_parsed is None:
        raise RuntimeError("JD extraction failed.")

    return response.output_parsed


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def load_registry() -> dict:
    ensure_project_dirs()

    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(SEED_REGISTRY, f, indent=2)

    return SEED_REGISTRY.copy()


def save_registry(registry: dict) -> None:
    ensure_project_dirs()
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def update_registry_from_jd(extraction: JDExtraction, registry: dict) -> dict:
    for entity in extraction.entities:
        key = normalize_name(entity.name)

        if key not in registry:
            registry[key] = {
                "canonical": entity.name.strip(),
                "category": entity.category,
                "adjacent": [],
                "seen": 1,
                "discovered_from_jd": True,
            }
        else:
            registry[key]["seen"] = registry[key].get("seen", 0) + 1
            if not registry[key].get("category"):
                registry[key]["category"] = entity.category

    save_registry(registry)
    return registry


def make_compact_laya_state(extraction: JDExtraction) -> dict:
    return {
        "title": extraction.target_title or "",
        "skills": [e.name for e in extraction.entities[:35]],
        "responsibilities": extraction.responsibilities[:8],
        "domain": extraction.domain_terms[:8],
    }


def _answer_choice(answer: dict) -> str:
    return answer.get("choice") or answer.get("value") or answer.get("answer")


def _answer_confidence(answer: dict):
    return answer.get("confidence")


def _answer_noul(answer: dict) -> float:
    value = answer.get("noul", answer.get("probability", answer.get("value", 0.0)))
    return float(value)


def classify_role_with_laya(extraction: JDExtraction, laya_agent) -> dict:
    state = make_compact_laya_state(extraction)

    questions = {
        "primary_family": {
            "type": "choice",
            "instructions": "Which job family is the PRIMARY focus of this job?",
            "criteria": FAMILY_CRITERIA,
        },
        "seniority": {
            "type": "choice",
            "instructions": "What seniority level best represents this job?",
            "criteria": {
                "entry": "entry level, junior, graduate",
                "mid": "experienced individual contributor",
                "senior": "senior individual contributor",
                "lead": "lead, principal, staff or architect",
                "manager": "people or program management responsibility",
            },
        },
        "hybrid_role": {
            "type": "noul",
            "instructions": "Does this job materially combine two or more technical job families?",
        },
    }

    result = laya_agent.predict(state, questions)
    answers = result["answers"]
    primary_answer = answers["primary_family"]
    seniority_answer = answers["seniority"]
    primary = _answer_choice(primary_answer)

    secondary_questions = {
        "secondary_family": {
            "type": "choice",
            "instructions": (
                f"The primary job family is {primary}. "
                "Which SECONDARY family is materially represented? "
                "Choose none if there is no meaningful secondary family."
            ),
            "criteria": {**FAMILY_CRITERIA, "none": "no meaningful secondary family"},
        }
    }

    secondary_result = laya_agent.predict({**state, "primary_family": primary}, secondary_questions)
    secondary = _answer_choice(secondary_result["answers"]["secondary_family"])

    if secondary == primary:
        secondary = "none"

    role = {
        "primary_family": primary,
        "primary_confidence": _answer_confidence(primary_answer),
        "secondary_family": secondary,
        "seniority": _answer_choice(seniority_answer),
        "seniority_confidence": _answer_confidence(seniority_answer),
        "hybrid_probability": _answer_noul(answers["hybrid_role"]),
    }
    return refine_role_with_deterministic_signals(extraction, role)


def refine_role_with_deterministic_signals(extraction: JDExtraction, role: dict) -> dict:
    text_parts = [extraction.target_title or ""]
    text_parts.extend(entity.name for entity in extraction.entities)
    text_parts.extend(extraction.responsibilities)
    text_parts.extend(extraction.domain_terms)
    text = normalize_name(" ".join(text_parts))

    scores = {}
    for family, terms in FAMILY_SIGNAL_TERMS.items():
        scores[family] = sum(1 for term in terms if term in text)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < 2:
        role["deterministic_family_scores"] = scores
        return role

    current = role.get("primary_family")
    top_family, top_score = ranked[0]
    second_family, second_score = ranked[1] if len(ranked) > 1 else ("none", 0)

    if current not in scores or top_score >= scores.get(current, 0) + 2:
        role["primary_family"] = top_family
        role["primary_confidence"] = max(role.get("primary_confidence") or 0.0, 0.88)
        role["deterministic_family_override"] = True

    if second_family != role["primary_family"] and second_score >= 2:
        role["secondary_family"] = second_family
        role["hybrid_probability"] = max(float(role.get("hybrid_probability") or 0.0), 0.75)
    elif role.get("secondary_family") == role.get("primary_family"):
        role["secondary_family"] = "none"

    if (
        role["primary_family"] == "devops_cloud"
        and scores.get("data_engineering", 0) >= 3
        and {"databricks", "spark"} <= set(term for term in FAMILY_SIGNAL_TERMS["data_engineering"] if term in text)
    ):
        role["secondary_family"] = "data_engineering"
        role["hybrid_probability"] = max(float(role.get("hybrid_probability") or 0.0), 0.80)
        role["deterministic_secondary_override"] = True

    title = normalize_name(extraction.target_title or "")
    if "senior" in title and role.get("seniority") not in {"lead", "principal", "staff"}:
        role["seniority"] = "senior"
        role["seniority_confidence"] = max(role.get("seniority_confidence") or 0.0, 0.90)
        role["deterministic_seniority_override"] = True

    role["deterministic_family_scores"] = scores
    return role


def classify_mentioned_entities(extraction: JDExtraction, laya_agent) -> dict:
    state = make_compact_laya_state(extraction)
    mentioned = [e for e in extraction.entities if e.requirement == "mentioned"]

    if not mentioned:
        return {}

    questions = {}
    for i, entity in enumerate(mentioned):
        questions[f"entity_{i}"] = {
            "type": "choice",
            "instructions": (
                f"Determine the resume priority of '{entity.name}' "
                f"for this specific JD. Evidence: {entity.evidence}"
            ),
            "criteria": {
                "P1": "central mandatory capability",
                "P2": "important job requirement",
                "P3": "useful or preferred technology",
                "P4": "minor or contextual technology",
            },
        }

    result = laya_agent.predict(state, questions)
    priorities = {}

    for i, entity in enumerate(mentioned):
        answer = result["answers"][f"entity_{i}"]
        priorities[entity.name] = {
            "priority": _answer_choice(answer),
            "confidence": _answer_confidence(answer),
        }

    return priorities


def collect_adjacent_candidates(extraction: JDExtraction, registry: dict, max_candidates=20) -> list:
    direct_names = {normalize_name(e.name) for e in extraction.entities}
    candidates = {}

    for entity in extraction.entities:
        key = normalize_name(entity.name)
        record = registry.get(key)

        if not record:
            continue

        for adjacent in record.get("adjacent", []):
            adj_key = normalize_name(adjacent)

            if adj_key in direct_names:
                continue

            if adj_key not in candidates:
                candidates[adj_key] = {
                    "name": adjacent,
                    "parent": entity.name,
                }

            if len(candidates) >= max_candidates:
                return list(candidates.values())

    return list(candidates.values())


def validate_adjacent_with_laya(extraction: JDExtraction, candidates: list, laya_agent, threshold=0.68) -> list:
    if not candidates:
        return []

    state = make_compact_laya_state(extraction)
    questions = {}

    for i, candidate in enumerate(candidates):
        questions[f"adj_{i}"] = {
            "type": "noul",
            "instructions": (
                f"Is '{candidate['name']}' a DIRECTLY relevant adjacent technology "
                f"for this exact job description, given the explicitly mentioned "
                f"technology '{candidate['parent']}'? Reject generic or weak associations."
            ),
        }

    result = laya_agent.predict(state, questions)
    approved = []

    for i, candidate in enumerate(candidates):
        probability = _answer_noul(result["answers"][f"adj_{i}"])
        if probability >= threshold:
            approved.append(
                {
                    **candidate,
                    "priority": "P4",
                    "source": "approved_adjacent",
                    "relevance_probability": probability,
                }
            )

    return approved


def placement_rules(priority: str, category: str) -> list[str]:
    sections = ["technical_skills"]

    if priority in {"P1", "P2"}:
        sections.append("experience_responsibilities")

    if priority == "P1":
        sections.append("professional_summary")

    if priority == "P3":
        sections.append("selected_experience")

    if priority == "P4":
        sections = ["technical_skills_optional"]

    if category in {"ai_tool", "ai_framework"} and priority in {"P1", "P2"}:
        if "experience_responsibilities" not in sections:
            sections.append("experience_responsibilities")

    return sections


def entity_appears_in_responsibility(entity_name: str, extraction: JDExtraction) -> bool:
    name = normalize_name(entity_name)
    aliases = {name}
    if name == "openai":
        aliases.add("openai api")
    if name == "claude":
        aliases.add("claude api")
    if name == "spark":
        aliases.add("apache spark")
    responsibility_text = normalize_name(" ".join(extraction.responsibilities))
    return any(alias in responsibility_text for alias in aliases)


def upgrade_priority_for_responsibility(priority: str, entity, extraction: JDExtraction) -> str:
    if priority in {"P1", "P2"}:
        return priority
    if entity_appears_in_responsibility(entity.name, extraction):
        return "P2"
    if entity.category in {"ai_tool", "ai_framework"} and entity_appears_in_responsibility(entity.name, extraction):
        return "P2"
    return priority


def jd_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_blueprint(jd_text: str, extraction: JDExtraction, registry: dict, laya_agent) -> dict:
    role = classify_role_with_laya(extraction, laya_agent)
    mentioned_priorities = classify_mentioned_entities(extraction, laya_agent)

    entity_records = []
    priority_groups = {"P1": [], "P2": [], "P3": [], "P4": []}

    for entity in extraction.entities:
        if entity.requirement in EXPLICIT_PRIORITY:
            priority = EXPLICIT_PRIORITY[entity.requirement]
            confidence = 1.0
        else:
            classification = mentioned_priorities.get(
                entity.name,
                {"priority": "P3", "confidence": None},
            )
            priority = classification["priority"]
            confidence = classification["confidence"]

        priority = upgrade_priority_for_responsibility(priority, entity, extraction)

        record = {
            "name": entity.name,
            "category": entity.category,
            "priority": priority,
            "source": "jd_direct",
            "requirement": entity.requirement,
            "evidence": entity.evidence,
            "confidence": confidence,
            "placement": placement_rules(priority, entity.category),
        }

        entity_records.append(record)
        priority_groups[priority].append(entity.name)

    candidates = collect_adjacent_candidates(extraction, registry)
    approved_adjacent = validate_adjacent_with_laya(extraction, candidates, laya_agent)

    for item in approved_adjacent:
        priority_groups["P4"].append(item["name"])
        entity_records.append(
            {
                "name": item["name"],
                "category": "adjacent",
                "priority": "P4",
                "source": "approved_adjacent",
                "parent_skill": item["parent"],
                "confidence": item["relevance_probability"],
                "placement": ["technical_skills_optional"],
            }
        )

    for priority in priority_groups:
        priority_groups[priority] = list(dict.fromkeys(priority_groups[priority]))

    allowed_technologies = list(dict.fromkeys(item["name"] for item in entity_records))

    return {
        "blueprint_version": "1.0",
        "jd_hash": jd_hash(jd_text),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "target_title": extraction.target_title,
            "company": extraction.company_name,
            **role,
        },
        "priority_skills": priority_groups,
        "entities": entity_records,
        "responsibilities": extraction.responsibilities,
        "domain_terms": extraction.domain_terms,
        "certifications": [
            {
                "name": name,
                "requirement": "mentioned",
                "evidence": "jd_extraction",
                "source": "jd_direct",
                "candidate_verified": False,
            }
            for name in extraction.certifications
        ],
        "generation_contract": {
            "allowed_technologies": allowed_technologies,
            "allow_new_llm_skills": False,
            "allowed_sources": ["jd_direct", "approved_adjacent"],
            "rules": [
                "Resume must remain centered on the target JD.",
                "P1 skills receive strongest emphasis.",
                "P2 skills receive strong supporting emphasis.",
                "P3 skills may appear where naturally relevant.",
                "P4 skills are supporting/adjacent only.",
                "Do not introduce unrelated technologies.",
                "Do not change the primary job-family identity.",
                "Hybrid secondary family may be represented when present.",
                "Explicit AI tools should appear in responsibilities when P1 or P2.",
                "Every technology used must exist in allowed_technologies.",
            ],
        },
        "quality_gates": {
            "P1_coverage_min": 1.00,
            "P2_coverage_min": 0.90,
            "unapproved_skill_count_max": 0,
            "duplicate_bullet_count_max": 0,
            "role_drift_allowed": False,
            "technology_drift_allowed": False,
        },
    }


def save_blueprint(blueprint: dict) -> Path:
    ensure_project_dirs()
    path = BLUEPRINT_DIR / f"{blueprint['jd_hash']}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(blueprint, f, indent=2, ensure_ascii=False)

    history_record = {
        "jd_hash": blueprint["jd_hash"],
        "created_at": blueprint["created_at"],
        "target_title": blueprint["job"]["target_title"],
        "primary_family": blueprint["job"]["primary_family"],
        "secondary_family": blueprint["job"]["secondary_family"],
        "P1": blueprint["priority_skills"]["P1"],
        "P2": blueprint["priority_skills"]["P2"],
        "P3": blueprint["priority_skills"]["P3"],
        "P4": blueprint["priority_skills"]["P4"],
    }

    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(history_record, ensure_ascii=False) + "\n")

    return path


def run_phase_1(jd_text: str) -> tuple[dict, Path]:
    ensure_project_dirs()
    load_environment()

    client = OpenAI()
    laya_agent = load_laya_agent()
    registry = load_registry()

    extraction = extract_jd(jd_text, client)
    registry = update_registry_from_jd(extraction, registry)
    blueprint = build_blueprint(jd_text, extraction, registry, laya_agent)
    blueprint_path = save_blueprint(blueprint)

    return blueprint, blueprint_path


def print_blueprint_summary(blueprint: dict, blueprint_path: Path) -> None:
    print("=" * 70)
    print("JD BLUEPRINT CREATED")
    print("=" * 70)
    print("\nTarget Role:", blueprint["job"]["target_title"])
    print("Primary Family:", blueprint["job"]["primary_family"])
    print("Secondary Family:", blueprint["job"]["secondary_family"])
    print("Hybrid Probability:", blueprint["job"]["hybrid_probability"])
    print("\nP1:", blueprint["priority_skills"]["P1"])
    print("\nP2:", blueprint["priority_skills"]["P2"])
    print("\nP3:", blueprint["priority_skills"]["P3"])
    print("\nP4:", blueprint["priority_skills"]["P4"])
    print("\nAllowed technologies:", blueprint["generation_contract"]["allowed_technologies"])
    print("\nSaved:", blueprint_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 1 JD blueprint JSON.")
    parser.add_argument("--jd-file", required=True, help="Path to a text file containing the full JD.")
    parser.add_argument("--print-json", action="store_true", help="Print the complete blueprint JSON.")
    args = parser.parse_args()

    jd_text = Path(args.jd_file).read_text(encoding="utf-8")
    blueprint, blueprint_path = run_phase_1(jd_text)
    print_blueprint_summary(blueprint, blueprint_path)

    if args.print_json:
        print(json.dumps(blueprint, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
