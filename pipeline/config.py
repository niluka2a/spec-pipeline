"""Pipeline configuration and environment-backed defaults."""

import os

# Single fallback variable for all stages.
DEFAULT_MODEL = os.environ.get("PIPELINE_MODEL", "")

MODEL_PLANNING = os.environ.get(
    "PIPELINE_MODEL_PLANNING",
    DEFAULT_MODEL or "claude-sonnet-4-6",
)
MODEL_IMPLEMENTATION = os.environ.get(
    "PIPELINE_MODEL_IMPLEMENTATION",
    DEFAULT_MODEL or "claude-haiku-4-5",
)
MODEL_TEST_GENERATION = os.environ.get(
    "PIPELINE_MODEL_TEST_GENERATION",
    DEFAULT_MODEL or "claude-haiku-4-5",
)
