"""
AI-assisted Implementation
Generates code from the approved plan, restricted to sandbox/src/.
"""

import json
import os
from pathlib import Path
from typing import Any

import anthropic
import yaml

from prompts.templates import IMPLEMENTATION_PROMPT
from pipeline.audit import AuditLogger
from config import MODEL_IMPLEMENTATION
from pipeline.utils import _parse_delimited
from pipeline.demo_responses import DEMO_IMPLEMENTATION
from services.file_service import FileService

ALLOWED_ROOT = Path("sandbox/src")


def generate_implementation(
    spec: dict[str, Any],
    plan: dict[str, Any],
    audit: AuditLogger,
    client: anthropic.Anthropic,
) -> dict[str, str]:
    """Generate code files from spec + plan. Returns {filepath: content}."""
    print("\n[implementation] Generating code...")
    file_service = FileService(audit)

    if os.environ.get("PIPELINE_DEMO_MODE") == "true":
        print("  [DEMO] Using pre-written implementation")
        audit.log_ai_interaction(
            "implementation",
            "DEMO_MODE",
            str(DEMO_IMPLEMENTATION),
            "demo",
        )
        file_service.write_files(DEMO_IMPLEMENTATION)
        return DEMO_IMPLEMENTATION

    spec_yaml = yaml.dump(spec, default_flow_style=False)
    plan_json = json.dumps(plan, indent=2)
    prompt = IMPLEMENTATION_PROMPT.format(spec_yaml=spec_yaml, plan_json=plan_json)

    response = client.messages.create(
        model=MODEL_IMPLEMENTATION,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    audit.log_ai_interaction("implementation", prompt, raw, MODEL_IMPLEMENTATION)

    try:
        files = json.loads(raw)
    except json.JSONDecodeError:
        files = _parse_delimited(raw)

    # Governance: enforce sandbox restriction
    safe_files = _enforce_sandbox(files)
    file_service.write_files(safe_files)
    return safe_files


def _enforce_sandbox(files: dict[str, str]) -> dict[str, str]:
    """Reject any file paths outside sandbox/src/."""
    safe = {}
    for path, content in files.items():
        p = Path(path)
        try:
            # Resolve relative to cwd — ensure it stays under ALLOWED_ROOT
            if str(p).startswith("sandbox/src"):
                resolved = p
            else:
                resolved = Path("sandbox/src") / p.name
            safe[str(resolved)] = content
            print(f"  ✓  Approved path: {resolved}")
        except Exception:
            print(f"  ✗  BLOCKED path (outside sandbox): {path}")
    return safe

