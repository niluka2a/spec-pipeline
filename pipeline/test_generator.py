"""
Automated Test Generation
Generates pytest unit, integration, and acceptance tests mapped to AC criteria.
"""

import json
from pathlib import Path
from typing import Any

import anthropic
import yaml

from prompts.templates import TEST_GENERATION_PROMPT
from pipeline.audit import AuditLogger

MODEL = "claude-sonnet-4-20250514"


def generate_tests(
    spec: dict[str, Any],
    implementation_files: dict[str, str],
    audit: AuditLogger,
    client: anthropic.Anthropic,
) -> dict[str, str]:
    """Generate test files mapped to spec acceptance criteria."""
    print("\n[test-gen] Generating tests...")

    spec_yaml = yaml.dump(spec, default_flow_style=False)

    # Summarise what was implemented (file names + first 300 chars each)
    impl_summary = "\n\n".join(
        f"### {path}\n{content[:300]}..." for path, content in implementation_files.items()
    )

    ac_list = "\n".join(
        f"- {ac.get('id', '?')}: {ac.get('description', '')}"
        for ac in spec.get("acceptance_criteria", [])
    )

    prompt = TEST_GENERATION_PROMPT.format(
        spec_yaml=spec_yaml,
        implementation_summary=impl_summary,
        acceptance_criteria=ac_list,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    audit.log_ai_interaction("test_generation", prompt, raw, MODEL)

    try:
        test_files = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        test_files = json.loads(cleaned)

    # Write test files
    for path, content in test_files.items():
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        audit.log_generated_file(str(p), "test", len(content))
        print(f"  🧪  Written: {p}  ({len(content)} chars)")

    return test_files
