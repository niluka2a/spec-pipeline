"""
Automated Test Generation
Generates pytest unit, integration, and acceptance tests mapped to AC criteria.
"""

import json
import os
from pathlib import Path
from typing import Any

import anthropic
import yaml

from pipeline.demo_responses import DEMO_TESTS
from prompts.templates import TEST_GENERATION_PROMPT
from pipeline.audit import AuditLogger
from config import MODEL_TEST_GENERATION
from pipeline.utils import _parse_delimited
from services.file_service import FileService


def generate_tests(
    spec: dict[str, Any],
    implementation_files: dict[str, str],
    audit: AuditLogger,
    client: anthropic.Anthropic,
) -> dict[str, str]:
    """Generate test files mapped to spec acceptance criteria."""
    print("\n[test-gen] Generating tests...")
    file_service = FileService(audit)

    if os.environ.get("PIPELINE_DEMO_MODE") == "true":
        print("  [DEMO] Using pre-written tests")
        audit.log_ai_interaction(
            "test_generation",
            "DEMO_MODE",
            str(DEMO_TESTS),
            "demo",
        )
        file_service.write_files(
            DEMO_TESTS,
            file_type="test",
            display_icon="🧪",
        )
        return DEMO_TESTS

    spec_yaml = yaml.dump(spec, default_flow_style=False)

    # Summarise what was implemented (file names + first 300 chars each)
    impl_summary = "\n\n".join(
        f"### {path}\n{content[:300]}..."
        for path, content in implementation_files.items()
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
        model=MODEL_TEST_GENERATION,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    audit.log_ai_interaction("test_generation", prompt, raw, MODEL_TEST_GENERATION)

    try:
        test_files = json.loads(raw)
    except json.JSONDecodeError:
        test_files = _parse_delimited(raw)

    # Write test files
    file_service.write_files(
        test_files,
        file_type="test",
        display_icon="🧪",
    )
    return test_files
