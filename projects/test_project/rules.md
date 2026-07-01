Focus only on requirement quality from a QA perspective.

---

PRIORITIES (in order):

1. Evidence-based findings (mandatory)
2. QA impact (testability, correctness, security)
3. Non-generic relevance to this requirement

---

ALLOWED FINDINGS:

- contradictions
- ambiguous validations
- missing state transitions
- role/permission gaps
- negative scenarios
- timeout/expiration behavior
- integration uncertainty (only if explicitly mentioned)
- security/privacy risks (only if directly implied)

---

STRICT EVIDENCE RULE:

- Every finding must include explicit evidence from:
  1. requirement text OR
  2. project context

- Evidence must:
  - reference exact phrases or logic from input
  - not rely on general knowledge

- If no evidence exists → omit the finding

---

ASSUMPTION RULE (limited):

- Assumptions are allowed ONLY if:
  - they arise from a direct ambiguity in the requirement
  - they are minimal and clearly stated
  - they are marked as "assumption-based"

- Do not introduce external system behavior

---

PROHIBITED:

- generic QA recommendations
- industry-standard risks not grounded in input
- distributed system concerns unless explicitly stated
- implementation advice unless it affects testability
- vague or duplicate findings

---

OUTPUT CONTROL:

- Prefer fewer high-confidence findings over many weak ones
- If unsure → omit
- Max 5 items per section (risks, scenarios, questions)

---

QUESTIONS FOR PO:

Must:
- be specific
- unblock testing
- clarify behavior
- be directly tied to a finding

Avoid:
- vague or generic questions