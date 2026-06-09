"""
Planning Layer
Converts a validated spec into a structured implementation plan using Claude.
"""

import json
import sys
from typing import Any

import anthropic
import yaml

from prompts.templates import PLANNING_PROMPT
from pipeline.audit import AuditLogger

MODEL = "claude-sonnet-4-20250514"


def generate_plan(
    spec: dict[str, Any],
    audit: AuditLogger,
    client: anthropic.Anthropic,
) -> dict[str, Any]:
    """Call Claude to produce an implementation plan from the spec."""
    print("\n[planning] Generating implementation plan...")

    spec_yaml = yaml.dump(spec, default_flow_style=False)
    # Format the prompt with the YAML spec embedded.
    prompt = PLANNING_PROMPT.format(spec_yaml=spec_yaml)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    audit.log_ai_interaction("planning", prompt, raw, MODEL)

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        # Try stripping accidental markdown fences
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        plan = json.loads(cleaned)

    _print_plan(plan)
    return plan


def _print_plan(plan: dict[str, Any]) -> None:
    print("\n  📋 Technical Design Summary:")
    print(f"     {plan.get('technical_design_summary', 'N/A')}")

    tasks = plan.get("implementation_tasks", [])
    print(f"\n  📌 Implementation Tasks ({len(tasks)}):")
    for t in tasks:
        effort = t.get("estimated_effort", "?")
        print(f"     [{effort.upper()}] {t['id']}: {t['title']}")

    risks = plan.get("risk_considerations", [])
    if risks:
        print(f"\n  ⚠  Risks ({len(risks)}):")
        for r in risks:
            print(f"     - {r}")

    modules = plan.get("impacted_modules", [])
    print(f"\n  📁 Impacted modules: {', '.join(modules) if modules else 'none specified'}")
    print(f"\n  🧪 Test strategy: {plan.get('test_strategy', 'N/A')}")
