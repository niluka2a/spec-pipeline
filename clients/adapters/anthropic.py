"""Anthropic LLM adapter."""
import anthropic

from clients.ai_client import AIClient


class AnthropicAIClient:
    """Adapter for Anthropic's client to the AIClient protocol."""

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def request(self, prompt: str, model: str, max_tokens: int) -> str:
        """Send a prompt to Claude via Anthropic and return the response text."""
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
