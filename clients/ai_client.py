"""AI client interface (Protocol)."""
from typing import Protocol


class AIClient(Protocol):
    """Protocol for LLM clients. Decouples code from specific implementations."""

    def request(self, prompt: str, model: str, max_tokens: int) -> str:
        """Send a prompt to an LLM and return the model text output."""
