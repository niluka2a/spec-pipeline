import json
import re


def _parse_json(raw: str) -> dict:
    """Robustly extract JSON from Claude response."""
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find the outermost { ... } block
    start = cleaned.find("{")
    end = cleaned.rfind("}")          # rfind gets the LAST } not the first
    if start != -1 and end != -1:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response (length={len(raw)}):\n{cleaned[:500]}")