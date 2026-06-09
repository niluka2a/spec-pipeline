"""
AI-assisted Implementation
Generates code from the approved plan, restricted to sandbox/src/.
"""

import json
from pathlib import Path
from typing import Any

import anthropic
import yaml

from prompts.templates import IMPLEMENTATION_PROMPT
from pipeline.audit import AuditLogger

MODEL = "claude-sonnet-4-20250514"
ALLOWED_ROOT = Path("sandbox/src")


def generate_implementation(
    spec: dict[str, Any],
    plan: dict[str, Any],
    audit: AuditLogger,
    client: anthropic.Anthropic,
) -> dict[str, str]:
    """Generate code files from spec + plan. Returns {filepath: content}."""
    print("\n[implementation] Generating code...")

    spec_yaml = yaml.dump(spec, default_flow_style=False)
    plan_json = json.dumps(plan, indent=2)
    prompt = IMPLEMENTATION_PROMPT.format(spec_yaml=spec_yaml, plan_json=plan_json)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    audit.log_ai_interaction("implementation", prompt, raw, MODEL)

    try:
        files = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        files = json.loads(cleaned)

    # Governance: enforce sandbox restriction
    safe_files = _enforce_sandbox(files)
    _write_files(safe_files, audit)
    return safe_files


def _enforce_sandbox(files: dict[str, str]) -> dict[str, str]:
    """Reject any file paths outside sandbox/src/."""
    safe = {}
    for path, content in files.items():
        p = Path(path)
        try:
            # Resolve relative to cwd — ensure it stays under ALLOWED_ROOT
            resolved = Path("sandbox/src") / p.name if not str(p).startswith("sandbox/src") else p
            safe[str(resolved)] = content
            print(f"  ✓  Approved path: {resolved}")
        except Exception:
            print(f"  ✗  BLOCKED path (outside sandbox): {path}")
    return safe


def _write_files(files: dict[str, str], audit: AuditLogger) -> None:
    """Write generated files to disk."""
    for path, content in files.items():
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        audit.log_generated_file(str(p), "implementation", len(content))
        print(f"  📄  Written: {p}  ({len(content)} chars)")
