"""Factory for creating AI client adapters.

This centralises provider selection and construction logic so the rest of
the codebase can remain provider-agnostic.
"""
from typing import Optional
import os

from clients.ai_client import AIClient


def create_client(provider: Optional[str] = None, api_key: Optional[str] = None, demo_mode: Optional[bool] = None) -> AIClient:
    """Create an `AIClient` for the requested provider.

    Args:
        provider: Optional provider name (e.g. 'anthropic'). If None, reads
            `PIPELINE_AI_PROVIDER` environment variable (defaults to 'anthropic').
        api_key: Optional API key for the provider. If None, reads provider-specific
            env vars (e.g. `ANTHROPIC_API_KEY`).
        demo_mode: If True, create a client suitable for demo mode (if adapter
            supports it). If None, reads `PIPELINE_DEMO_MODE` env var.
    """
    provider = provider or os.getenv("PIPELINE_AI_PROVIDER", "anthropic")
    demo = demo_mode if demo_mode is not None else (os.getenv("PIPELINE_DEMO_MODE") == "true")

    if provider == "anthropic":
        # Local import to avoid hard dependency at module import time
        import anthropic
        from clients.adapters.anthropic import AnthropicAIClient

        key = api_key or os.getenv("ANTHROPIC_API_KEY") or ("demo" if demo else None)
        if not demo and not key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable not set and not in demo mode")

        return AnthropicAIClient(anthropic.Anthropic(api_key=key))

    raise ValueError(f"Unsupported AI provider: {provider}")
