"""
Spec Intake & Validation
Parses and validates feature specs in YAML, JSON, or Markdown.
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = [
    "feature_objective",
    "user_story",
    "business_rules",
    "acceptance_criteria",
    "non_functional_requirements",
    "out_of_scope",
]


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_spec(path: str) -> dict[str, Any]:
    """Load a spec file from YAML, JSON, or Markdown (YAML front-matter)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Spec file not found: {path}")

    content = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()

    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(content)

    if suffix == ".json":
        return json.loads(content)

    if suffix == ".md":
        # Extract YAML front-matter between --- delimiters
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if match:
            return yaml.safe_load(match.group(1))
        raise ValueError("Markdown spec must contain YAML front-matter between --- delimiters")

    raise ValueError(f"Unsupported spec format: {suffix}. Use .yaml, .json, or .md")


def validate_spec(spec: dict[str, Any]) -> ValidationResult:
    """Check all required fields exist and are non-empty."""
    errors = []
    warnings = []

    for field_name in REQUIRED_FIELDS:
        if field_name not in spec:
            errors.append(f"Missing required field: '{field_name}'")
        elif not spec[field_name]:
            errors.append(f"Field '{field_name}' is empty")

    # Acceptance criteria must be a list with at least one item
    ac = spec.get("acceptance_criteria", [])
    if isinstance(ac, list):
        if len(ac) == 0:
            errors.append("acceptance_criteria must contain at least one criterion")
        for i, item in enumerate(ac):
            if isinstance(item, dict) and "id" not in item:
                warnings.append(f"acceptance_criteria[{i}] has no 'id' field — traceability will be limited")
    else:
        errors.append("acceptance_criteria must be a list")

    if "spec_version" not in spec:
        warnings.append("No 'spec_version' found — versioning recommended for auditability")

    if "feature_id" not in spec:
        warnings.append("No 'feature_id' found — recommend adding one for traceability")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def load_and_validate(path: str) -> dict[str, Any]:
    """Load spec and validate it. Prints results and exits on failure."""
    print(f"[spec-intake] Loading spec from: {path}")
    spec = load_spec(path)

    print("[spec-intake] Validating spec...")
    result = validate_spec(spec)

    for w in result.warnings:
        print(f"  ⚠  WARNING: {w}")

    if not result.valid:
        for e in result.errors:
            print(f"  ✗  ERROR: {e}")
        print("[spec-intake] Validation FAILED. Pipeline halted.")
        sys.exit(1)

    print(f"  ✓  Spec valid — {len(spec.get('acceptance_criteria', []))} acceptance criteria found")
    return spec
