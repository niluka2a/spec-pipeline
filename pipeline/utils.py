import json


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

    raise ValueError(
        "Could not parse JSON from response "
        f"(length={len(raw)}):\n{cleaned[:500]}"
    )

def _parse_delimited(raw: str) -> dict[str, str]:
    """Parse ===FILE: path=== delimited response — avoids JSON escaping issues."""
    files = {}
    parts = raw.split("===FILE:")
    for part in parts[1:]:  # skip preamble before first ===FILE:
        lines = part.split("\n")
        header = lines[0].strip().rstrip("===").strip()  # extract path
        content = (
            "\n".join(lines[1:])
            .split("===END===")[0]
            .split("===FILE:")[0]
            .strip()
        )
        if header and content:
            files[header] = content
    if not files:
        raise ValueError(
            "No ===FILE: blocks found in response:\n{raw[:300]}"
        )
    return files
