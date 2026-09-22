"""
Phase 2: Blueprint -> Resume JSON -> Validate -> Score -> Repair -> Learn

Run after Phase 1 has created a JD blueprint JSON.

Example:
    python3 phase_2_resume_pipeline.py \
      --blueprint resume_engine_data/blueprints/YOUR_BLUEPRINT.json \
      --resume-seed resume_seed.json \
      --variants 5 \
      --audit

Candidate mode is optional:
    python3 phase_2_resume_pipeline.py \
      --blueprint resume_engine_data/blueprints/YOUR_BLUEPRINT.json \
      --candidate-profile candidate_profile.json
"""

from resume_engine.main import main


if __name__ == "__main__":
    main()
