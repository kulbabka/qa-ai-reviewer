"""
draft_story.py

Formats raw, unstructured requirement text into a structured user story
draft ready for QA review.

The formatter preserves ambiguity, incompleteness, and contradictions —
it does NOT improve or complete the source requirement.
"""
import json
from typing import Any, Dict

from openai import OpenAI

from utils import extract_response_json


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

DRAFT_STORY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "formatted_story": {"type": "string"},
    },
    "required": ["title", "formatted_story"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def build_draft_story_prompt(
    project_context: str,
    glossary: str,
    raw_story: str,
) -> str:
    return f"""
You are a QA requirement formatter.

Your task:
Transform a raw task description into a structured requirement draft for QA review.

You MUST:
- structure the source text
- extract only explicitly stated information
- preserve ambiguity, incompleteness, and contradictions
- NOT improve, normalize, or complete the requirement

Return JSON only:
- title
- formatted_story

The formatted_story must use markdown and include:
- Feature
- Business goal
- Actors
- Preconditions
- Trigger
- Main flow
- Acceptance criteria
- Validation rules
- Open questions
- Out of scope

--------------------------------------------------
CORE PRINCIPLE

The output must reflect the source AS-IS.

If something is missing → keep it missing
If something is unclear → keep it unclear
If something is contradictory → keep the contradiction

Do NOT make the requirement look better than it is.

--------------------------------------------------
STRICT RULES

DO NOT:
- invent system behavior
- infer missing triggers, flows, validations, permissions, or preconditions
- convert assumptions into facts
- rewrite technical notes as confirmed behavior
- derive rules from general logic
- smooth over contradictions
- duplicate the same content across multiple sections unless explicitly justified

If information is not explicitly present:
→ write "Not specified."

--------------------------------------------------
SECTION RULES

Feature:
- Short neutral name derived from the source text

Business goal:
- Only business intent (NOT system behavior)
- Do NOT rewrite the full user story
- If unclear → "Not specified"

Actors:
- Only explicitly mentioned roles
- Do NOT infer additional actors

Preconditions:
- Only explicit
- Else → "Not specified."

Trigger:
- Only explicitly stated initiating events
- Do NOT infer from UI patterns (e.g., opening a form, clicking edit, submitting)
- Do NOT infer from the feature itself
- If not explicitly present → "Not specified."

Main flow:
- Include ONLY source-supported behavior statements
- Do NOT create step-by-step flow unless explicitly present
- Preserve original wording such as:
  - "Front end: ..."
  - "Back end: ..."
  - "should ..."
- Do NOT include:
  - acceptance criteria
  - constraints
  - permissions
  - high-level rules
  - exceptions
- Statements like:
  - "user can only..."
  - "only allowed..."
  - "must not..."
  MUST NOT be placed in Main flow unless explicitly written as a step

If no real flow exists:
→ keep minimal OR write "Not specified."

Acceptance criteria:
- Copy or lightly normalize ONLY explicitly stated AC
- Do NOT add new AC
- Do NOT move other content into AC

--------------------------------------------------
VALIDATION RULES (STRICT)

This section is OPTIONAL.

Include ONLY if:
- rules are explicitly defined in the source
- AND they are testable without missing data

A rule is testable only if:
- required inputs are defined
- expected outcome is clear

DO NOT include:
- acceptance criteria rewritten as rules
- UI behavior as rules
- technical instructions as rules
- high-level intent
- generalized or inferred constraints

If unclear → "Not specified."

Bad examples:

Source:
"Front end: disable or hide restricted fields"

Wrong:
- Restricted fields are disabled

Correct:
Validation rules:
Not specified.

---

Source:
"Only permitted fields can be updated"

Wrong:
- Only permitted fields can be updated

Why:
Not testable (field set undefined)

Correct:
Validation rules:
Not specified.

--------------------------------------------------
OPEN QUESTIONS

Purpose:
Capture missing information required for testing.

Include ONLY:
- missing definitions (e.g. field lists)
- contradictions
- unclear role/permission logic
- undefined behavior
- missing API/UI outcomes

Each question must:
- directly unblock a test scenario

DO NOT include:
- wording issues
- naming inconsistencies (e.g. email vs e-mail)
- generic or vague questions

--------------------------------------------------
OUT OF SCOPE

- Include only if explicitly stated or clearly implied
- Else → "Not specified."

--------------------------------------------------
SELF-CHECK (MANDATORY)

Before finalizing:

Trigger:
- Explicitly present? If NO → "Not specified."

Main flow:
- Only source-supported statements?
- No AC inside?
- No constraints/rules inside?

Validation rules:
- Explicit? If NO → remove
- Testable? If NO → remove
- If none → "Not specified."

Open questions:
- Each question improves testability?
- If not → remove

Final:
- Did I structure, not improve?
- Did I preserve ambiguity?
- Did I avoid filling gaps?

--------------------------------------------------
PROJECT CONTEXT:
{project_context}

GLOSSARY:
{glossary}

RAW STORY:
{raw_story}
""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draft_story(
    client: OpenAI,
    model: str,
    project_context: str,
    glossary: str,
    raw_story: str,
) -> Dict[str, str]:
    """
    Format a raw requirement text into a structured story draft.

    Returns {"title": str, "formatted_story": str}
    """
    prompt = build_draft_story_prompt(
        project_context=project_context,
        glossary=glossary,
        raw_story=raw_story,
    )

    response = client.responses.create(
        model=model,
        input=prompt,
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "draft_story",
                "schema": DRAFT_STORY_SCHEMA,
                "strict": True,
            }
        },
    )

    return extract_response_json(response)
