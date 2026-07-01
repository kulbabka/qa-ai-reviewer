# QA AI Reviewer

A Streamlit-based AI assistant for QA engineers that catches requirement issues, generates test cases from screenshots, and performs UX analysis — before bugs make it to production.

---

## The Problem It Solves

QA work traditionally starts too late. By the time a tester sees a ticket, ambiguities are already baked into the implementation. Common pain points:

- **Vague requirements** that slip through refinement unchallenged — missing definitions, contradictions, non-testable acceptance criteria
- **Test cases written from assumptions** rather than from what's actually in the UI
- **UX issues discovered late** in the cycle when fixing them is expensive

This tool brings AI into the QA process at the earliest possible stage — before a single line of code is written or a test case is drafted.

---

## What It Does

The app has three analysis modes, each targeting a different QA scenario:

### Mode 1 — Requirement Review
Paste or upload a raw ticket, user story, or requirement text. The AI first formats it into a structured user story (without cleaning up ambiguities), then runs a **two-pass review** to find:

- Contradictions
- Ambiguities
- Missing definitions
- Risks
- Non-testable requirements

Output includes categorized findings with severity (`low / medium / high`), confidence scores, evidence, and a list of prioritized questions to ask the Product Owner.

### Mode 2 — Flow → Test Cases
Upload screenshots of a UI flow. The AI extracts **observable facts** from the actual UI (not assumptions), which you can review and edit. Then it generates high-level test cases grounded in what's visually present, plus a list of assumptions and unknowns to investigate.

### Mode 3 — UX Review
Point the AI at a product feature — via screenshots, documentation URLs, or a text description — and it performs a structured UX analysis. Findings are classified by type:

- Silent failure
- Ambiguous state
- Missing control
- Missing feedback
- Plan gate UX
- Business gap
- Confusing behavior

Each finding includes severity, user impact, business impact, and a concrete suggestion. The review produces an overall UX score (0–10) with a summary assessment.

### Mode 4 — Project Settings
Manage project configuration files directly in the UI: create new projects, edit `context.md`, `glossary.md`, `rules.md`, and `product_context.md`.

---

## Project Structure

```
qa_ai_reviewer/
├── app.py                  # Main Streamlit UI
├── reviewer.py             # Two-pass requirement review logic
├── draft_story.py          # Requirement formatter
├── ui_flow_cases.py        # Flow → test cases generation
├── ui_image_extract.py     # Screenshot fact extraction
├── ux_review.py            # UX analysis logic
├── doc_fetcher.py          # Fetches content from documentation URLs
├── url_fetcher.py          # URL content fetching utilities
├── utils.py                # Shared helpers
├── requirements.txt
├── .env.example
├── templates/
│   └── story_template.md   # User story template
└── projects/
    ├── README.md           # How to set up projects
    ├── test_project/       # Starter template
    └── coupler_scheduler/  # Example: Coupler.io scheduler review
```

Each project under `projects/` is a self-contained configuration:

```
projects/your_project/
├── context.md          # QA scope — what is and isn't being reviewed (required)
├── glossary.md         # Domain terminology for consistent findings (optional)
├── rules.md            # What the AI should focus on or deprioritize (optional)
└── product_context.md  # Product description, audience, feature context (required for Mode 3)
```

Review outputs are saved to `outputs/{project_name}/` as JSON files.

---

## Setup

### Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys) with access to `gpt-4o` or `gpt-4o-mini`

### Install

```bash
git clone <your-repo-url>
cd qa_ai_reviewer

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4o
```

`OPENAI_MODEL` must support the Responses API. For Mode 2 (screenshots), it must also support vision. Recommended: `gpt-4o`. For lower cost: `gpt-4o-mini`.

---

## Running

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Adding a New Project

1. Create `projects/my_project/`
2. Add `context.md` (required) — describe what's in scope for QA
3. Add `product_context.md` if you plan to use Mode 3 (UX Review)
4. Optionally add `glossary.md` and `rules.md`

See `projects/coupler_scheduler/` for a real-world example, and `projects/test_project/` for blank templates.

---

## Tech Stack

| Component | Library |
|-----------|---------|
| UI | Streamlit 1.50 |
| AI | OpenAI Python SDK (`gpt-4o`) |
| Image handling | Pillow |
| Data | Pandas |
| Config | python-dotenv |
