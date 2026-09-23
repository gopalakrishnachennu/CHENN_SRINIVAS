import argparse
import json
import subprocess
import sys
from pathlib import Path

from resume_engine.pipeline.phase2_pipeline import run_phase2_pipeline
from resume_engine.reports.behavioral_audit import run_behavioral_audit, save_behavioral_audit
from resume_engine.reports.implementation_audit import (
    run_implementation_audit,
    save_implementation_audit,
)


def _run_fixture_tests() -> bool:
    """Run the pytest behavioral fixture test suite and print results."""
    project_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_behavioral_fixtures.py", "-v", "--tb=short"],
        cwd=str(project_root),
        capture_output=False,
        check=False,
    )
    return result.returncode == 0


def _print_phase25_report(impl_audit, behavioral_audit, pytest_passed: bool | None = None) -> None:
    """Print the Phase 2.5 completion report to stdout."""
    sep = "=" * 60
    print()
    print(sep)
    print("PHASE 2.5 — BEHAVIORAL VALIDATION & HARDENING REPORT")
    print(sep)
    print()
    print(f"Implementation Audit : {impl_audit.implemented_count}/{impl_audit.total_count} modules ({impl_audit.implementation_percent:.1f}%)")
    print(f"Behavioral Audit     : {behavioral_audit['result']}")
    if pytest_passed is not None:
        print(f"Pytest Fixture Tests : {'PASS' if pytest_passed else 'FAIL'}")
    print()
    print("BEHAVIORAL CHECKS")
    for k, v in behavioral_audit["checks"].items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print()
    print("PASS CONDITIONS")
    for k, v in behavioral_audit["pass_conditions"].items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print()
    fixture_info = behavioral_audit.get("fixture_assertions", {})
    print(f"Fixture JDs          : {behavioral_audit['fixture_inventory']['count']}")
    print(f"Fixture assertions   : {fixture_info.get('assertion_count', '?')}")
    print(f"All fixtures covered : {fixture_info.get('all_fixtures_have_assertions', False)}")
    print()
    print(f"OVERALL RESULT: {behavioral_audit['result']}")
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 resume JSON generation and validation pipeline.")
    parser.add_argument("--blueprint", default=None, help="Path to JD_BLUEPRINT.json from Phase 1.")
    parser.add_argument("--resume-seed", default="resume_seed.json", help="Path to template-mode resume seed JSON.")
    parser.add_argument("--candidate-profile", default=None, help="Optional truthful candidate profile JSON for candidate mode.")
    parser.add_argument("--variants", type=int, default=5, help="Number of variants to generate.")
    parser.add_argument("--model", default=None, help="Optional OpenAI model override.")
    parser.add_argument("--run-id", default=None, help="Optional run ID (UUID generated automatically if omitted).")
    parser.add_argument("--no-repair", action="store_true", help="Disable targeted repair pass.")
    parser.add_argument("--skip-laya", action="store_true", help="Skip Laya semantic validation.")
    parser.add_argument(
        "--export",
        default=None,
        help="Phase 3: comma-separated export formats for validated finals (docx,pdf).",
    )
    parser.add_argument("--audit", action="store_true", help="Run implementation audit after pipeline.")
    parser.add_argument("--behavioral-audit", action="store_true", help="Run Phase 2.5 behavioral audit after pipeline.")
    parser.add_argument("--run-fixture-tests", action="store_true", help="Run behavioral pytest fixture tests (no OpenAI required).")
    parser.add_argument("--phase25-report", action="store_true", help="Print full Phase 2.5 completion report.")
    args = parser.parse_args()

    # Offline-only modes — no blueprint required
    if args.run_fixture_tests:
        print("Running Phase 2.5 behavioral fixture tests...")
        passed = _run_fixture_tests()
        print(f"\nFixture tests: {'PASS' if passed else 'FAIL'}")
        if not args.phase25_report:
            sys.exit(0 if passed else 1)

    if args.phase25_report:
        impl = run_implementation_audit()
        save_implementation_audit(impl)
        behavioral = run_behavioral_audit()
        save_behavioral_audit(behavioral)
        pytest_passed = _run_fixture_tests() if not args.run_fixture_tests else None
        _print_phase25_report(impl, behavioral, pytest_passed)
        sys.exit(0 if behavioral["result"] == "PASS" else 1)

    if args.blueprint is None:
        parser.error("--blueprint is required unless using --run-fixture-tests or --phase25-report")

    export_formats = None
    if args.export:
        export_formats = [part.strip().lower() for part in args.export.split(",") if part.strip()]

    result = run_phase2_pipeline(
        blueprint_path=args.blueprint,
        resume_seed_path=args.resume_seed,
        candidate_profile_path=args.candidate_profile,
        variant_limit=args.variants,
        model=args.model,
        repair=not args.no_repair,
        use_laya=not args.skip_laya,
        run_id=args.run_id,
        export_formats=export_formats,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.audit:
        audit = run_implementation_audit()
        json_path, txt_path = save_implementation_audit(audit)
        print(f"Implementation audit saved: {json_path}")
        print(f"Human-readable audit saved: {txt_path}")

    if args.behavioral_audit:
        behavioral = run_behavioral_audit()
        json_path, txt_path = save_behavioral_audit(behavioral)
        print(f"Behavioral audit saved: {json_path}")
        print(f"Human-readable behavioral audit saved: {txt_path}")


if __name__ == "__main__":
    main()
