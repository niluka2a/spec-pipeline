"""
Quality Gates
Runs automated validation: linting, type checking, tests, security scan.
Pipeline fails hard if any required gate fails.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pipeline.audit import AuditLogger


@dataclass
class GateResult:
    name: str
    passed: bool
    output: str
    required: bool = True


def _run(cmd: list[str], cwd: str | None = None) -> tuple[bool, str]:
    """Run a subprocess and return (success, combined output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except FileNotFoundError as e:
        return False, f"Tool not found: {e}"


def _sandbox_source_files() -> list[str]:
    """Return top-level sandbox source files, excluding nested auth packages."""
    return [str(p) for p in Path("sandbox/src").glob("*.py")]


def _test_directories() -> list[str]:
    """Return the directory that should be used for pytest runs.

    The generated test suite is expected to live under sandbox/tests so we
    prefer that location and only fall back to the repo-level tests directory
    if needed.
    """
    if Path("sandbox/tests").exists():
        return ["sandbox/tests"]
    if Path("tests").exists():
        return ["tests"]
    return ["tests"]


def run_quality_gates(audit: AuditLogger, base_dir: str = ".") -> bool:
    """Run all quality gates. Returns True only if all required gates pass."""
    print("\n[quality-gates] Running validation checks...")
    gates: list[GateResult] = []

    # 1. Linting with ruff
    print("  → Linting (ruff)...")
    passed, output = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            *(_sandbox_source_files()),
            "pipeline/",
            "--select",
            "E,F,W",
        ],
        cwd=base_dir,
    )
    gates.append(GateResult("lint:ruff", passed, output))

    # 2. Type checking with mypy
    print("  → Type checking (mypy)...")
    passed, output = _run(
        [
            sys.executable,
            "-m",
            "mypy",
            *(_sandbox_source_files()),
            "--ignore-missing-imports",
            "--no-strict-optional",
            "--explicit-package-bases",
        ],
        cwd=base_dir,
    )
    gates.append(GateResult("typecheck:mypy", passed, output))

    # 3. Test execution with pytest
    print("  → Running tests (pytest)...")
    test_dirs = _test_directories()
    passed, output = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            *test_dirs,
            "-v",
            "--tb=short",
            "--no-header",
        ],
        cwd=base_dir,
    )
    gates.append(GateResult("tests:pytest", passed, output))

    # 4. Basic security scan with bandit (optional gate — warn only)
    print("  → Security scan (bandit)...")
    passed, output = _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            *(_sandbox_source_files()),
            "-ll",
            "-q",
        ],
        cwd=base_dir,
    )
    gates.append(GateResult("security:bandit", passed, output, required=False))

    # Report results
    print()
    all_required_passed = True
    for gate in gates:
        status = (
            "✓  PASS"
            if gate.passed
            else ("✗  FAIL" if gate.required else "⚠  WARN")
        )
        label = f"[{'REQUIRED' if gate.required else 'OPTIONAL'}]"
        print(f"  {status}  {gate.name} {label}")
        if not gate.passed and gate.output:
            for line in gate.output.split("\n")[:8]:  # show first 8 lines
                print(f"         {line}")

        audit.log_quality_gate(gate.name, gate.passed, gate.output)

        if gate.required and not gate.passed:
            all_required_passed = False

    if not all_required_passed:
        print("\n[quality-gates] ✗ One or more required gates FAILED. Pipeline halted.")
    else:
        print("\n[quality-gates] ✓ All required gates passed.")

    return all_required_passed
