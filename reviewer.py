"""
reviewer.py

Two-pass QA requirement review using the OpenAI Responses API.

Pass 1 — generate findings, questions, assessment from scratch.
Pass 2 — verify, deduplicate, and sharpen the first-pass output.

Can also be run from the CLI for quick ad-hoc reviews.
"""
import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

from utils import extract_response_json


# ---------------------------------------------------------------------------
# JSON Schema — must stay in sync with both pass prompts
# ---------------------------------------------------------------------------

FINDING_TYPES = [
    "contradiction",
    "ambiguity",
    "missing_definition",
    "risk",
    "non_testable_requirement",   # FIX: was referenced in second-pass prompt but missing from schema
]

REVIEW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": FINDING_TYPES,
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "title": {"type": "string"},
                    "details": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": [
                    "type",
                    "severity",
                    "title",
                    "details",
                    "why_it_matters",
                    "evidence",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "questions_for_po": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": ["priority", "question", "reason", "confidence"],
                "additionalProperties": False,
            },
        },
        "overall_assessment": {
            "type": "object",
            "properties": {
                "requirement_clarity_score": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "summary": {"type": "string"},
            },
            "required": ["requirement_clarity_score", "summary"],
            "additionalProperties": False,
        },
    },
    "required": ["findings", "questions_for_po", "overall_assessment"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# File helpers (used by both reviewer.py CLI and app.py)
# ---------------------------------------------------------------------------

def read_text_file(path: Path, required: bool = True) -> str:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required file not found: {path}")
        return ""
    return path.read_text(encoding="utf-8").strip()


def get_project_paths(project_name: str) -> Dict[str, Path]:
    project_root = Path("projects") / project_name
    return {
        "root": project_root,
        "context": project_root / "context.md",
        "glossary": project_root / "glossary.md",
        "rules": project_root / "rules.md",
        "stories": project_root / "stories",
        "output": Path("outputs") / project_name,
    }


# ---------------------------------------------------------------------------
# Pass 1 — generate
# ---------------------------------------------------------------------------

def build_first_pass_prompt(
    project_context: str,
    glossary: str,
    rules: str,
    story: str,
) -> str:
    types_list = "\n".join(f"- {t}" for t in FINDING_TYPES)
    return f"""
You are a strict QA requirements review assistant.

Goal:
Identify QA-relevant issues in the requirement.

Return:
- findings (typed)
- questions_for_po
- overall_assessment

Finding types (use exact strings):
{types_list}

Type definitions:
- contradiction           → direct logical conflict within the requirement
- ambiguity               → multiple reasonable interpretations exist
- missing_definition      → required behavior, data, or rule is not defined
- risk                    → grounded QA risk caused by the requirement as written
- non_testable_requirement → requirement cannot be verified or tested as written

Rules:
- Each finding = one distinct issue
- Do not duplicate
- Use evidence from requirement text or project context only
- Prefer fewer high-confidence findings
- Max 8 findings

Confidence:
- high   → explicitly stated in input
- medium → clear logical inference
- low    → avoid; omit the finding instead

--------------------------------------------------
CROSS-SECTION & COMPLETENESS CHECKS

Do not only scan sentence-by-sentence for explicit "not specified" gaps.
Actively check for these four patterns, which require reading the WHOLE
story together, not one line at a time:

1. Cross-section conflicts — does a constraint or scope statement in one
   part of the story (e.g. "must also support X") clash with the stated
   purpose or timing assumption in another part? A requirement can list
   all its pieces individually and still be internally inconsistent when
   those pieces are combined. Flag this as "contradiction", not
   "missing_definition".

2. Incomplete state coverage — for every user action or system event the
   story describes (e.g. dismiss, retry, cancel, expire), check whether
   the requirement defines what happens AFTER it. An action with no
   defined resulting state is a gap even if the action itself is named.

3. Requirements hidden in informal text — sections like "Notes",
   "Context", or parenthetical asides often contain real functional
   requirements (e.g. "should also track X for analytics"), not just
   background color. Evaluate informal notes with the same scrutiny as
   formal acceptance criteria — do not treat them as out of scope by
   default.

4. Delivery risk — if the story states a deadline or urgency alongside
   unresolved open questions you identified above, raise a "risk" finding
   about shipping with unresolved ambiguity, not just the individual gaps.

--------------------------------------------------

PROJECT CONTEXT:
{project_context}

GLOSSARY:
{glossary}

REVIEW RULES:
{rules}

USER STORY:
{story}
""".strip()


# ---------------------------------------------------------------------------
# Pass 2 — verify and sharpen
# ---------------------------------------------------------------------------

def build_second_pass_prompt(
    project_context: str,
    glossary: str,
    rules: str,
    story: str,
    first_pass_result: Dict[str, Any],
) -> str:
    first_pass_json = json.dumps(first_pass_result, ensure_ascii=False, indent=2)
    types_list = "\n".join(f"- {t}" for t in FINDING_TYPES)

    return f"""
You are a strict QA review verifier.

You must:
- NOT re-analyze from scratch
- ONLY refine the first-pass results below

Tasks:
1. Remove weak or speculative findings
2. Merge duplicates into the stronger one
3. Fix incorrectly typed findings
4. Keep only QA-critical findings

--------------------------------------------------
CRITICAL PRESERVATION

Do NOT remove findings related to:
- persistence behavior (full reject vs partial save)
- conflicting system behavior
- authorization rules
- UI behavior conflicts
- testability problems
- cross-section conflicts (a constraint in one part of the story clashing
  with the purpose/timing assumed in another part)
- incomplete state coverage (a named user action with no defined
  resulting state, e.g. what happens after dismiss/retry/expire)
- functional requirements hidden in informal Notes/Context sections
- delivery risk from shipping with unresolved open questions under a
  stated deadline

--------------------------------------------------
PRIORITY RULE

Prefer findings affecting:
1. persistence / data integrity
2. authorization
3. acceptance / rejection behavior
4. UI behavior
5. testability

Over:
- response formatting
- error message wording
- cosmetic issues

--------------------------------------------------
DECOMPOSITION RULE

If a finding contains multiple issues:
- separate them conceptually
- preserve the highest-impact issue

Specifically:
- atomic vs partial save MUST be standalone
- do NOT merge it with response formatting or generic validation wording

--------------------------------------------------
CLASSIFICATION RULE

Allowed types (use exact strings):
{types_list}

Definitions:
- contradiction           → direct logical conflict
- ambiguity               → multiple reasonable interpretations
- missing_definition      → required behavior/data is not defined
- risk                    → grounded QA risk from the requirement
- non_testable_requirement → cannot be verified without missing information

Do NOT default everything to ambiguity.

--------------------------------------------------
TESTABILITY CHECK

A requirement is non_testable_requirement if:
- required input data is not defined
- expected observable outcome is not defined
- it references undefined rules, configurations, or data sets

ANTI-DUPLICATION:
- If missing_definition already fully covers the issue, do NOT also add
  non_testable_requirement for the same gap
- Only use non_testable_requirement when it adds a distinct testability angle

--------------------------------------------------
OUTPUT RULES

- Target 4–6 strong findings
- Remove weak findings without mercy
- Keep high-impact findings even if uncomfortable
- Every finding must cite evidence from the story or project context
- Return only JSON — no preamble, no markdown fences

--------------------------------------------------
PROJECT CONTEXT:
{project_context}

GLOSSARY:
{glossary}

REVIEW RULES:
{rules}

USER STORY:
{story}

FIRST PASS OUTPUT:
{first_pass_json}
""".strip()


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

def call_model(client: OpenAI, model: str, prompt: str) -> Dict[str, Any]:
    response = client.responses.create(
        model=model,
        input=prompt,
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "qa_review",
                "schema": REVIEW_SCHEMA,
                "strict": True,
            }
        },
    )
    return extract_response_json(response)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review_requirement_two_pass(
    client: OpenAI,
    model: str,
    project_context: str,
    glossary: str,
    rules: str,
    story: str,
) -> Dict[str, Any]:
    """
    Run a two-pass review of a requirement.

    Pass 1: generate findings, questions, assessment.
    Pass 2: verify, deduplicate, and sharpen the first-pass output.

    Returns the final verified result dict.
    """
    first = call_model(
        client,
        model,
        build_first_pass_prompt(project_context, glossary, rules, story),
    )

    final = call_model(
        client,
        model,
        build_second_pass_prompt(project_context, glossary, rules, story, first),
    )

    return final


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="QA requirement reviewer (CLI)")
    parser.add_argument("project", help="Project name under ./projects/")
    parser.add_argument("story_file", help="Path to the story .md or .txt file")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set in environment or .env file.")

    client = OpenAI(api_key=api_key)
    paths = get_project_paths(args.project)

    project_context = read_text_file(paths["context"], required=True)
    glossary = read_text_file(paths["glossary"], required=False)
    rules = read_text_file(paths["rules"], required=False)
    story = read_text_file(Path(args.story_file), required=True)

    print(f"Reviewing: {args.story_file} (project: {args.project})\n")
    result = review_requirement_two_pass(
        client=client,
        model=model,
        project_context=project_context,
        glossary=glossary,
        rules=rules,
        story=story,
    )

    output_dir = paths["output"]
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.story_file).stem
    output_path = output_dir / f"{stem}_review.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved to: {output_path}")
    print(f"\nClarity score: {result['overall_assessment']['requirement_clarity_score']}/10")
    print(f"Findings: {len(result['findings'])}")
    print(f"Questions for PO: {len(result['questions_for_po'])}")


if __name__ == "__main__":
    _cli()
