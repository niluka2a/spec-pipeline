"""
Human Approval Workflow
Lightweight CLI-based approval checkpoints for governance.
In CI/CD this would be replaced by a webhook or PR review gate.
"""

import os
from typing import Any

from pipeline.audit import AuditLogger


def _is_ci() -> bool:
    """Detect if running in a non-interactive CI environment."""
    return os.environ.get("CI", "").lower() in ("true", "1", "yes")


def _auto_approve_mode() -> bool:
    return os.environ.get("PIPELINE_AUTO_APPROVE", "").lower() in ("true", "1", "yes")


def request_approval(
    stage: str,
    context: dict[str, Any],
    audit: AuditLogger,
) -> bool:
    """
    Pause and ask a human to approve before proceeding.
    Returns True if approved, False if rejected.

    In CI mode with PIPELINE_AUTO_APPROVE=true, auto-approves.
    """
    print(f"\n{'='*60}")
    print(f"  ⏸  APPROVAL REQUIRED: {stage}")
    print(f"{'='*60}")

    for key, value in context.items():
        if isinstance(value, str) and len(value) < 200:
            print(f"  {key}: {value}")
        elif isinstance(value, list):
            print(f"  {key}: {value[:3]}{'...' if len(value) > 3 else ''}")

    print()

    # Auto-approve in CI or when env var set
    if _is_ci() or _auto_approve_mode():
        print("  [CI MODE] Auto-approving...")
        audit.log_approval(stage, approved=True, approver="ci-auto")
        return True

    while True:
        response = input("  Approve? [y/n]: ").strip().lower()
        if response == "y":
            audit.log_approval(stage, approved=True, approver="human-cli")
            print(f"  ✓  Approved: {stage}")
            return True
        elif response == "n":
            audit.log_approval(stage, approved=False, approver="human-cli")
            print(f"  ✗  Rejected: {stage}. Pipeline halted.")
            return False
        else:
            print("  Please enter 'y' or 'n'.")
