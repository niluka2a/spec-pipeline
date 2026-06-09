"""
Prompt templates for each pipeline stage.
Keeping prompts here (not buried in code) makes them versionable and auditable.
"""

PLANNING_PROMPT = """You are a senior software architect. Given the feature specification below,
produce a structured implementation plan as a JSON object.

FEATURE SPECIFICATION:
{spec_yaml}

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{{
  "technical_design_summary": "...",
  "implementation_tasks": [
    {{"id": "T-001", "title": "...", "description": "...", "estimated_effort": "small|medium|large"}}
  ],
  "impacted_modules": ["path/to/module.py"],
  "risk_considerations": ["..."],
  "test_strategy": "..."
}}"""


IMPLEMENTATION_PROMPT = """You are a senior Python developer. Generate clean, production-quality
Python code based on the approved implementation plan and feature spec below.

FEATURE SPEC:
{spec_yaml}

IMPLEMENTATION PLAN:
{plan_json}

CONSTRAINTS:
- Only generate files within the sandbox/src/ directory
- Use type hints throughout
- Include docstrings on all public functions and classes
- No external dependencies beyond Python stdlib unless clearly justified
- Code must be directly runnable

Return ONLY a JSON object mapping file paths to file contents (no markdown):
{{
  "sandbox/src/filename.py": "...full file content...",
  "sandbox/src/another.py": "...full file content..."
}}"""


TEST_GENERATION_PROMPT = """You are a test engineer. Generate comprehensive pytest tests for the
implementation below. Each test must map back to the acceptance criteria IDs from the spec.

FEATURE SPEC:
{spec_yaml}

GENERATED IMPLEMENTATION:
{implementation_summary}

ACCEPTANCE CRITERIA TO COVER:
{acceptance_criteria}

Requirements:
- Unit tests for each function/class
- Integration tests for the main flow
- At least one test per acceptance criterion (tag with the AC ID in the test name or docstring)
- Use pytest fixtures where appropriate
- Tests must be self-contained (no external services)

Return ONLY a JSON object mapping test file paths to file contents:
{{
  "tests/test_unit.py": "...full pytest file...",
  "tests/test_integration.py": "...full pytest file..."
}}"""
