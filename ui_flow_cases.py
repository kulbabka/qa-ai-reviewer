"""
ui_flow_cases.py

Generates structured high-level test cases from observed UI facts and
an optional task description.

Returns:
    {
        "flow_title": str,
        "observed_facts": [str, ...],
        "high_level_test_cases": [
            {
                "title": str,
                "purpose": str,
                "steps": [str, ...],
                "expected_result": str,
                "evidence_basis": str,
                "confidence": "high" | "medium" | "low"
            },
            ...
        ],
        "assumptions_and_unknowns": [str, ...]
    }
"""
import json
from typing import Any, Dict

from openai import OpenAI

from utils import extract_response_json


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

UI_FLOW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "flow_title": {
            "type": "string",
            "description": "Short, descriptive title for this UI flow.",
        },
        "observed_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Cleaned and normalised version of the input observed facts. "
                "Remove duplicates; keep each item atomic."
            ),
        },
        "high_level_test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short test case name.",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "What this test case validates.",
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered action steps. Each step is one action.",
                    },
                    "expected_result": {
                        "type": "string",
                        "description": "Observable outcome that confirms the test passed.",
                    },
                    "evidence_basis": {
                        "type": "string",
                        "description": (
                            "Which observed fact(s) or task text this test case "
                            "is derived from."
                        ),
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": (
                            "high = fully grounded in observed facts; "
                            "medium = partially grounded, minor inference; "
                            "low = mostly inferred — flag as assumption-based."
                        ),
                    },
                },
                "required": [
                    "title",
                    "purpose",
                    "steps",
                    "expected_result",
                    "evidence_basis",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "assumptions_and_unknowns": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Gaps, assumptions, or open questions that could affect test "
                "coverage or expected results."
            ),
        },
    },
    "required": [
        "flow_title",
        "observed_facts",
        "high_level_test_cases",
        "assumptions_and_unknowns",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(
    project_context: str,
    task_text: str,
    ui_observations: str,
) -> str:
    task_section = (
        f"TASK / REQUIREMENT TEXT:\n{task_text}"
        if task_text
        else "TASK / REQUIREMENT TEXT:\nNot provided."
    )

    return f"""
You are a QA analyst generating high-level test cases from UI evidence.

---

GOAL:
Produce testable, concrete, high-level test cases grounded strictly in what
is observable. Do not invent behavior that is not supported by evidence.

---

RULES:

Scope:
- Cover happy path, negative / error paths, boundary conditions, and
  permission/access scenarios — but ONLY if the observations support them.
- Do NOT generate test cases for backend behavior unless it is explicitly
  described in the task text.
- Do NOT test implementation details (e.g., API response codes) unless
  the task says so.

Steps:
- Each step = one user action or one system reaction.
- Use plain language: "Click [button]", "Enter [value] in [field]", "Observe [result]".
- Do NOT mix multiple actions in one step.

Expected result:
- Must be observable and verifiable.
- Describe what the user sees or what state the system reaches.
- Avoid vague results like "works correctly" or "success".

Confidence:
- high   → test case is fully grounded in observed facts or task text
- medium → test case requires a small inference (clearly stated)
- low    → test case is largely assumption-based; mark it explicitly

Assumptions and unknowns:
- Flag anything that would change test cases if clarified.
- Format: "Assumption: [statement]" or "Unknown: [question]"

Anti-patterns to avoid:
- Do NOT duplicate test cases that cover the same scenario.
- Do NOT create a test case just because a field exists — there must be
  an observable behavior to verify.
- Do NOT include "verify the page loads" as a standalone test case unless
  an empty/error state is explicitly visible.

Volume:
- Aim for 5–10 test cases. Prefer fewer high-confidence cases over many
  weak ones.

---

PROJECT CONTEXT:
{project_context or "Not provided."}

---

{task_section}

---

OBSERVED UI FACTS:
{ui_observations}

---

Return only valid JSON matching the schema. No preamble, no markdown fences.
""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ui_flow_test_cases(
    client: OpenAI,
    model: str,
    project_context: str,
    task_text: str,
    ui_observations: str,
) -> Dict[str, Any]:
    """
    Generate structured high-level test cases from UI observations.

    Args:
        client:          Initialised OpenAI client.
        model:           Model name (e.g. gpt-4o, gpt-4o-mini).
        project_context: Content of the project's context.md.
        task_text:       Optional task / requirement text for additional context.
        ui_observations: Newline-separated list of observed UI facts.

    Returns:
        {
            "flow_title": str,
            "observed_facts": [...],
            "high_level_test_cases": [...],
            "assumptions_and_unknowns": [...]
        }
    """
    prompt = _build_prompt(
        project_context=project_context,
        task_text=task_text,
        ui_observations=ui_observations,
    )

    response = client.responses.create(
        model=model,
        input=prompt,
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "ui_flow_test_cases",
                "schema": UI_FLOW_SCHEMA,
                "strict": True,
            }
        },
    )

    return extract_response_json(response)
