"""
Shared utilities for the QA AI Reviewer.
"""
import json
from typing import Any, Dict


def extract_response_json(response: Any) -> Dict[str, Any]:
    """
    Extract JSON payload from an OpenAI Responses API response.

    The Responses API can return the output in two shapes depending on
    the SDK version and response type:
      - response.output_text  (convenience accessor, newer SDK)
      - response.output[n].content[m].text  (raw output items)

    Raises ValueError if no JSON payload can be found.
    """
    # Convenience accessor (openai >= 2.x Responses API)
    output_text = getattr(response, "output_text", None)
    if output_text:
        return json.loads(output_text)

    # Fallback: walk output items
    for item in getattr(response, "output", []):
        for content_item in getattr(item, "content", []):
            if getattr(content_item, "type", None) == "output_text":
                return json.loads(content_item.text)

    raise ValueError(
        "Could not extract JSON from model response. "
        f"Response type: {type(response)}, "
        f"available attrs: {[a for a in dir(response) if not a.startswith('_')]}"
    )
