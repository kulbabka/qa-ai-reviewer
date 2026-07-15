"""
ux_review.py

Two-pass UX / feature review using the OpenAI Responses API.

Analyses a product feature from a UX and QA perspective:
- takes product context, feature description, and observed UI facts
- pass 1: generates UX findings
- pass 2: verifies, deduplicates, sharpens

Output schema matches the rendering expected by app.py (Mode 3).
"""
import json
from typing import Any, Dict

from openai import OpenAI

from utils import extract_response_json


# ---------------------------------------------------------------------------
# Constants — kept as single source of truth for schema + prompts
# ---------------------------------------------------------------------------

UX_FINDING_TYPES = [
    "silent_failure",       # system fails / stops with no clear in-app signal
    "ambiguous_state",      # UI can be interpreted multiple ways
    "missing_control",      # a needed config option does not exist
    "missing_feedback",     # action taken but no confirmation / preview given
    "plan_gate_ux",         # plan limit communicated too late or confusingly
    "business_gap",         # a real business use case with no supported path
    "confusing_behavior",   # works but behaves counter-intuitively
]

UX_SEVERITIES = ["critical", "high", "medium", "low"]

# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------

UX_REVIEW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": UX_FINDING_TYPES,
                    },
                    "severity": {
                        "type": "string",
                        "enum": UX_SEVERITIES,
                    },
                    "title": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "Clear description of the UX issue or gap.",
                    },
                    "configuration_used": {
                        "type": "string",
                        "description": (
                            "Exact UI configuration or steps that reproduce this issue. "
                            "Write 'N/A' for business gaps not tied to a specific config."
                        ),
                    },
                    "why_ux_issue": {
                        "type": "string",
                        "description": "Why this is a UX problem — which principle is violated.",
                    },
                    "user_impact": {
                        "type": "string",
                        "description": "Concrete impact on the end user.",
                    },
                    "business_impact": {
                        "type": "string",
                        "description": "Concrete impact on the business (retention, revenue, trust).",
                    },
                    "suggestion": {
                        "type": "string",
                        "description": "Actionable improvement recommendation.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": [
                    "type",
                    "severity",
                    "title",
                    "description",
                    "configuration_used",
                    "why_ux_issue",
                    "user_impact",
                    "business_impact",
                    "suggestion",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "overall_assessment": {
            "type": "object",
            "properties": {
                "feature_ux_score": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Overall UX quality score for this feature (1 = severely broken, 10 = excellent).",
                },
                "summary": {"type": "string"},
            },
            "required": ["feature_ux_score", "summary"],
            "additionalProperties": False,
        },
    },
    "required": ["findings", "overall_assessment"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Pass 1 — generate
# ---------------------------------------------------------------------------

def _build_first_pass_prompt(
    product_context: str,
    feature_description: str,
    ui_observations: str,
    documentation_context: str,
    rules: str = "",
) -> str:
    types_block = "\n".join(f"- {t}" for t in UX_FINDING_TYPES)

    doc_section = (
        f"DOCUMENTATION\n{documentation_context}"
        if documentation_context.strip()
        else "DOCUMENTATION\nNot provided."
    )

    rules_section = (
        f"REVIEW RULES / PRIORITIES\n{rules}"
        if rules.strip()
        else "REVIEW RULES / PRIORITIES\nNot provided — use default priority order (silent failures first)."
    )

    return f"""
You are a senior UX analyst and QA specialist conducting a feature UX review.

---
GOAL

Identify concrete UX issues and unsupported business scenarios for the feature
described below. Ground every finding in the provided observations, documentation,
and context.

---
FINDING TYPES (use exact strings)

{types_block}

Type definitions:
- silent_failure       → the system fails, stops, or produces unexpected results
                         without a clear in-app signal to the user
- ambiguous_state      → the UI shows a state or configuration that can be
                         reasonably interpreted in multiple ways
- missing_control      → a configuration option that users clearly need does
                         not exist in the UI
- missing_feedback     → the user performs an action but receives no
                         confirmation, preview, or result summary
- plan_gate_ux         → a plan limitation is communicated too late, is
                         invisible until the user hits it, or is presented in
                         a confusing way
- business_gap         → a realistic business use case that has no supported
                         path in the current feature
- confusing_behavior   → the feature works technically but behaves in a way
                         that contradicts user expectations or mental models

---
SEVERITY

- critical → causes data loss, silent incorrect results, or feature breakdown
- high     → causes wrong outcomes, major user confusion, or blocked workflows
- medium   → causes inconvenience, requires a workaround, or creates uncertainty
- low      → minor UX friction or a nice-to-have improvement

---
RULES

Evidence priority (use the best source available):
1. Observed UI facts — highest priority, directly visible
2. Documentation — use to understand intended behavior and surface gaps
   between what is documented and what the UI communicates
3. Product context — background, audience, and user goals

Do NOT raise generic UX best-practice issues unless directly supported by evidence.
Do NOT invent issues not grounded in the provided input.

Documentation-specific guidance:
- Use documentation to identify cases where the UI does not communicate
  behavior that is only described in help articles (users shouldn't need docs)
- Use documentation to find discrepancies between documented behavior and
  what is visible / inferable from the UI
- Do NOT simply restate what the documentation says — find the UX gap

Review rules guidance:
- If REVIEW RULES / PRIORITIES below lists a priority order, findings matching
  higher-priority categories should be surfaced first and covered more
  thoroughly than lower-priority ones.
- If it lists categories to deprioritize, do not raise findings that fall
  purely into those categories unless they are also a high/critical severity
  issue of another kind.

Confidence:
- high   → directly visible in observations or explicitly documented
- medium → reasonable inference from observations + context
- low    → avoid; omit the finding

Volume:
- Target 5–10 focused findings.
- Prefer fewer high-confidence findings.
- Do not duplicate findings with the same root issue.

---
{rules_section}

---
PRODUCT CONTEXT
{product_context or "Not provided."}

---
FEATURE DESCRIPTION
{feature_description or "Not provided."}

---
OBSERVED UI FACTS
{ui_observations or "Not provided."}

---
{doc_section}
""".strip()


# ---------------------------------------------------------------------------
# Pass 2 — verify and sharpen
# ---------------------------------------------------------------------------

def _build_second_pass_prompt(
    product_context: str,
    feature_description: str,
    ui_observations: str,
    documentation_context: str,
    first_pass_result: Dict[str, Any],
    rules: str = "",
) -> str:
    types_block = "\n".join(f"- {t}" for t in UX_FINDING_TYPES)
    first_json = json.dumps(first_pass_result, ensure_ascii=False, indent=2)

    doc_section = (
        f"DOCUMENTATION\n{documentation_context}"
        if documentation_context.strip()
        else "DOCUMENTATION\nNot provided."
    )

    rules_section = (
        f"REVIEW RULES / PRIORITIES\n{rules}"
        if rules.strip()
        else "REVIEW RULES / PRIORITIES\nNot provided."
    )

    return f"""
You are a UX review verifier.

You must:
- NOT re-analyse from scratch
- ONLY refine the first-pass findings below

---
TASKS

1. Remove findings that are generic, speculative, or not grounded in evidence.
2. Merge findings that describe the same root issue into the stronger one.
3. Fix incorrectly typed findings (use the type that best fits the root cause).
4. Sharpen descriptions, impacts, and suggestions — make each one concrete.
5. Ensure every suggestion is specific and actionable, not a platitude.
6. If documentation was provided, verify that findings correctly distinguish
   between "behavior not in the UI" vs "behavior not documented anywhere" —
   these have different severities and suggestions.
7. Re-check findings against REVIEW RULES / PRIORITIES below — drop findings
   that only match a deprioritized category, and make sure the surviving
   findings emphasize the prioritized categories.

---
CRITICAL PRESERVATION

Do NOT remove findings that describe:
- silent failures (feature stopping without in-app notification)
- state misrepresentation (UI shows active when actually paused/broken)
- plan gate issues where user wastes setup effort before hitting the wall
- missing controls for documented common business use cases
- behaviors that diverge from what the UI implies
- gaps between what documentation describes and what the UI communicates

---
CLASSIFICATION RULE

Allowed types (use exact strings):
{types_block}

Assign the type that matches the ROOT CAUSE, not the symptom.
Do NOT default everything to ambiguous_state.

---
SUGGESTION QUALITY RULE

Each suggestion must answer: "What exactly should be changed in the UI?"
Bad:  "Improve the error message."
Good: "Show a red 'Paused' badge on the flow card and disable the toggle
       visually when auto-refresh is suspended. Add an inline banner with
       the pause reason and a direct upgrade CTA."

---
IMPACT QUALITY RULE

User impact — name a concrete consequence:
Bad:  "Users may be confused."
Good: "A user who misses the email will assume the dashboard is live and
       make decisions based on stale data — potentially for days."

Business impact — name a retention or revenue risk:
Bad:  "This could hurt the business."
Good: "Power users who discover the silent pause late are high churn risk.
       Trust in the platform's reliability is the primary retention driver
       for this segment."

---
OUTPUT RULES

- Target 5–8 strong findings.
- Remove weak findings.
- Return only JSON — no preamble, no markdown.

---
PRODUCT CONTEXT
{product_context or "Not provided."}

FEATURE DESCRIPTION
{feature_description or "Not provided."}

OBSERVED UI FACTS
{ui_observations or "Not provided."}

{doc_section}

{rules_section}

FIRST PASS OUTPUT
{first_json}
""".strip()


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

def _call_model(client: OpenAI, model: str, prompt: str) -> Dict[str, Any]:
    response = client.responses.create(
        model=model,
        input=prompt,
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "ux_review",
                "schema": UX_REVIEW_SCHEMA,
                "strict": True,
            }
        },
    )
    return extract_response_json(response)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review_ux_feature(
    client: OpenAI,
    model: str,
    product_context: str,
    feature_description: str,
    ui_observations: str,
    documentation_context: str = "",
    rules: str = "",
) -> Dict[str, Any]:
    """
    Run a two-pass UX review of a feature.

    Args:
        client:                Initialised OpenAI client.
        model:                 Model name (e.g. gpt-4o).
        product_context:       Content of product_context.md for this project.
        feature_description:   Free-form description of the feature under review.
        ui_observations:       Newline-separated list of observed UI facts.
        documentation_context: Plain text fetched from documentation URLs,
                               pre-formatted by url_fetcher.results_to_context().
        rules:                 Content of rules.md for this project — priority
                               order and categories to deprioritize.

    Returns:
        {"findings": [...], "overall_assessment": {...}}
    """
    first = _call_model(
        client,
        model,
        _build_first_pass_prompt(
            product_context, feature_description,
            ui_observations, documentation_context, rules,
        ),
    )

    final = _call_model(
        client,
        model,
        _build_second_pass_prompt(
            product_context, feature_description,
            ui_observations, documentation_context, first, rules,
        ),
    )

    return final
