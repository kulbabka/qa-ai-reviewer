"""
ui_image_extract.py

Extracts structured observed facts from one or more UI screenshots
using the OpenAI Responses API with vision.

Returns:
    {
        "observed_facts": [str, ...],   # visible, concrete UI facts
        "unknowns": [str, ...]           # things visible but whose meaning is unclear
    }
"""
import base64
from typing import Any, Dict, List

from openai import OpenAI

from utils import extract_response_json


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

EXTRACT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "observed_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Concrete, visible facts extracted from the screenshots. "
                "Each item is a single, atomic, testable observation."
            ),
        },
        "unknowns": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Elements that are visible but whose meaning, behavior, or "
                "business rule cannot be determined from the screenshot alone."
            ),
        },
    },
    "required": ["observed_facts", "unknowns"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """
You are a QA analyst extracting observable UI facts from screenshots.

Your task:
Describe exactly what you see — not what you assume, infer, or expect.

---

OBSERVED FACTS rules:
- One fact per item. Keep each item atomic and concrete.
- Use factual language: "Button X is visible", "Field Y is disabled", "Label Z reads '...'".
- Do NOT infer business rules from visual appearance.
- Do NOT speculate about backend behavior.
- Do NOT describe what should happen — only what is visibly present.
- Include: visible fields, labels, buttons, states (enabled/disabled/checked),
  error messages, placeholders, icons, navigation elements, empty states,
  loading indicators, and any visible data.

UNKNOWNS rules:
- List elements that are present but whose purpose or behavior is not
  determinable from the screenshot alone.
- Format: "Unclear: [element] — [what is unknown about it]"
- Example: "Unclear: asterisk (*) next to Email field — unknown if it marks a required field or has another meaning"

---

PROJECT CONTEXT (use only to interpret labels and terminology):
{project_context}

---

Analyze all provided screenshots and return a combined, deduplicated list.
If multiple screenshots show the same screen in different states, note the
state differences as separate facts.
""".strip()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _encode_image(file_bytes: bytes, media_type: str) -> Dict[str, Any]:
    """Return an OpenAI Responses API content item for an image."""
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    return {
        "type": "input_image",
        "image_url": f"data:{media_type};base64,{b64}",
    }


def _resolve_media_type(filename: str) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "image/jpeg")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_ui_observed_facts_from_images(
    client: OpenAI,
    model: str,
    project_context: str,
    uploaded_files: List[Any],  # Streamlit UploadedFile objects
) -> Dict[str, Any]:
    """
    Send one or more screenshots to the model and extract observable UI facts.

    Args:
        client:          Initialised OpenAI client.
        model:           Model name (must support vision, e.g. gpt-4o).
        project_context: Content of the project's context.md.
        uploaded_files:  List of Streamlit UploadedFile objects.

    Returns:
        {"observed_facts": [...], "unknowns": [...]}
    """
    if not uploaded_files:
        return {"observed_facts": [], "unknowns": []}

    # Build the multimodal content list: images first, then the text prompt
    content: List[Dict[str, Any]] = []

    for uf in uploaded_files:
        raw_bytes = uf.read()
        media_type = _resolve_media_type(getattr(uf, "name", ""))
        content.append(_encode_image(raw_bytes, media_type))

    content.append({
        "type": "input_text",
        "text": EXTRACT_PROMPT.format(project_context=project_context or "Not provided."),
    })

    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "ui_observed_facts",
                "schema": EXTRACT_SCHEMA,
                "strict": True,
            }
        },
    )

    return extract_response_json(response)
