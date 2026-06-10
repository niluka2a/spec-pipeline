#!/usr/bin/env python3
"""
AI-native Spec-driven Development Pipeline
Main orchestrator — runs all stages end-to-end.

Usage:
    python run_pipeline.py specs/example_spec.yaml
    python run_pipeline.py specs/my_feature.json --run-id my-run-001
"""

import argparse
import sys
import os

import anthropic

from pipeline.spec_intake import load_and_validate
from pipeline.audit import AuditLogger
from pipeline.planner import generate_plan
from pipeline.implementer import generate_implementation
from pipeline.test_generator import generate_tests
from pipeline.quality_gates import run_quality_gates
from pipeline.approval import request_approval


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-native spec-driven development pipeline")
    parser.add_argument("spec", help="Path to feature spec file (.yaml, .json, or .md)")
    parser.add_argument("--run-id", help="Optional run identifier", default=None)
    parser.add_argument("--skip-gates", action="store_true", help="Skip quality gates (dev mode)")
    args = parser.parse_args()

    print("=" * 60)
    print("  🚀  AI-native Spec-driven Development Pipeline")
    print("=" * 60)

    # Initialise audit log
    audit = AuditLogger(run_id=args.run_id)
    print(f"  Run ID: {audit.run_id}\n")

    # Initialise Anthropic client
    demo_mode = os.environ.get("PIPELINE_DEMO_MODE") == "true"
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not demo_mode and not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key or "demo")

    # ── Stage 1: Spec Intake ─────────────────────────────────────────
    print("\n── STAGE 1: Spec Intake ─────────────────────────────")
    spec = load_and_validate(args.spec)
    audit.log_spec(spec, args.spec)

    # ── Stage 2: Planning ────────────────────────────────────────────
    print("\n── STAGE 2: Planning ────────────────────────────────")
    plan = generate_plan(spec, audit, client)

    # ── Approval Checkpoint 1: Before Implementation ─────────────────
    print("\n── APPROVAL CHECKPOINT 1 ────────────────────────────")
    approved = request_approval(
        stage="pre-implementation",
        context={
            "feature": spec.get("feature_name", "unknown"),
            "tasks": [t["title"] for t in plan.get("implementation_tasks", [])],
            "risks": plan.get("risk_considerations", []),
        },
        audit=audit,
    )
    if not approved:
        audit.log_pipeline_result(False, "Rejected at pre-implementation approval")
        sys.exit(1)

    # ── Stage 3: AI-assisted Implementation ─────────────────────────
    print("\n── STAGE 3: AI-assisted Implementation ──────────────")
    implementation_files = generate_implementation(spec, plan, audit, client)

    # ── Stage 4: Automated Test Generation ──────────────────────────
    print("\n── STAGE 4: Automated Test Generation ───────────────")
    test_files = generate_tests(spec, implementation_files, audit, client)

    # ── Stage 5: Quality Gates ───────────────────────────────────────
    if args.skip_gates:
        print("\n── STAGE 5: Quality Gates [SKIPPED] ─────────────────")
        gates_passed = True
    else:
        print("\n── STAGE 5: Quality Gates ───────────────────────────")
        gates_passed = run_quality_gates(audit)
        if not gates_passed:
            audit.log_pipeline_result(False, "Quality gates failed")
            sys.exit(1)

    # ── Approval Checkpoint 2: Before Deployment ────────────────────
    print("\n── APPROVAL CHECKPOINT 2 ────────────────────────────")
    approved = request_approval(
        stage="pre-deployment",
        context={
            "feature": spec.get("feature_name", "unknown"),
            "files_generated": list(implementation_files.keys()),
            "tests_generated": list(test_files.keys()),
            "quality_gates": "all passed" if gates_passed else "some failed",
        },
        audit=audit,
    )
    if not approved:
        audit.log_pipeline_result(False, "Rejected at pre-deployment approval")
        sys.exit(1)

    # ── Stage 6: Deployment Evidence ────────────────────────────────
    print("\n── STAGE 6: Deployment Evidence ─────────────────────")
    _write_deployment_manifest(spec, plan, implementation_files, test_files, audit)

    # ── Done ─────────────────────────────────────────────────────────
    summary = (
        f"Pipeline completed successfully. "
        f"{len(implementation_files)} implementation files, "
        f"{len(test_files)} test files generated."
    )
    audit.log_pipeline_result(True, summary)

    print("\n" + "=" * 60)
    print(f"  ✅  PIPELINE COMPLETE")
    print(f"  {summary}")
    print("=" * 60)


def _write_deployment_manifest(spec, plan, impl_files, test_files, audit: AuditLogger) -> None:
    """Write a deployment evidence manifest."""
    import json
    from pathlib import Path
    from datetime import datetime, timezone

    manifest = {
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "run_id": audit.run_id,
        "feature_id": spec.get("feature_id"),
        "feature_name": spec.get("feature_name"),
        "spec_version": spec.get("spec_version"),
        "implementation_files": list(impl_files.keys()),
        "test_files": list(test_files.keys()),
        "acceptance_criteria": [ac.get("id") for ac in spec.get("acceptance_criteria", [])],
    }

    path = Path(f"audit_logs/deployment_manifest_{audit.run_id}.json")
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  📦  Deployment manifest written: {path}")
    audit.log_generated_file(str(path), "deployment_manifest", len(json.dumps(manifest)))


if __name__ == "__main__":
    main()
