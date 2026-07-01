import json
import os
from pathlib import Path
from typing import Dict, List

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from reviewer import review_requirement_two_pass, read_text_file
from draft_story import draft_story
from ui_flow_cases import generate_ui_flow_test_cases
from ui_image_extract import extract_ui_observed_facts_from_images
from ux_review import review_ux_feature, UX_FINDING_TYPES
from url_fetcher import fetch_urls, results_to_context

load_dotenv()


# ── Project helpers ──────────────────────────────────────────────

def get_project_dirs() -> List[str]:
    projects_root = Path("projects")
    if not projects_root.exists():
        return []
    return sorted([p.name for p in projects_root.iterdir() if p.is_dir()])


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


def load_project_context(project_name: str) -> Dict[str, str]:
    paths = get_project_paths(project_name)
    return {
        "context": read_text_file(paths["context"], required=True),
        "glossary": read_text_file(paths["glossary"], required=False),
        "rules": read_text_file(paths["rules"], required=False),
        "product_context": read_text_file(
            paths["root"] / "product_context.md", required=False
        ),
    }


def save_ui_result(
    project_name: str, item_name: str, result: Dict, suffix: str = ""
) -> Path:
    output_dir = Path("outputs") / project_name
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(
        c if c.isalnum() or c in ("-", "_") else "_" for c in item_name
    ).strip("_") or "adhoc_item"
    filename = f"{safe_name}{suffix}.json" if suffix else f"{safe_name}.json"
    output_path = output_dir / filename
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


# ── Render helpers ───────────────────────────────────────────────

def render_finding(finding: Dict, index: int) -> None:
    type_labels = {
        "contradiction": "Contradiction",
        "ambiguity": "Ambiguity",
        "missing_definition": "Missing definition",
        "risk": "Risk",
        "non_testable_requirement": "Non-testable requirement",
    }
    with st.container(border=True):
        st.markdown(f"**{index}. {finding['title']}**")
        st.caption(
            f"Type: {type_labels.get(finding['type'], finding['type'])} "
            f"| Severity: {finding['severity'].upper()} "
            f"| Confidence: {finding['confidence']}"
        )
        st.write(finding["details"])
        st.markdown(f"**Why it matters:** {finding['why_it_matters']}")
        st.markdown(f"**Evidence:** {finding['evidence']}")


def render_question(question: Dict, index: int) -> None:
    with st.container(border=True):
        st.markdown(f"**{index}. {question['question']}**")
        st.caption(
            f"Priority: {question['priority']} | Confidence: {question['confidence']}"
        )
        st.write(question["reason"])


def render_test_case(tc: Dict, index: int) -> None:
    with st.container(border=True):
        st.markdown(f"**{index}. {tc['title']}**")
        st.caption(f"Confidence: {tc['confidence']}")
        st.markdown(f"**Purpose:** {tc['purpose']}")
        st.markdown("**Steps:**")
        for step in tc["steps"]:
            st.markdown(f"- {step}")
        st.markdown(f"**Expected result:** {tc['expected_result']}")
        st.markdown(f"**Evidence basis:** {tc['evidence_basis']}")


_SEV_EMOJI = {"critical": "", "high": "", "medium": "", "low": ""}
_TYPE_LABELS = {
    "silent_failure": "Silent failure",
    "ambiguous_state": "Ambiguous state",
    "missing_control": "Missing control",
    "missing_feedback": "Missing feedback",
    "plan_gate_ux": "Plan gate UX",
    "business_gap": "Business gap",
    "confusing_behavior": "Confusing behavior",
}


def render_ux_finding(finding: Dict, index: int) -> None:
    with st.container(border=True):
        st.markdown(
            f"**{_SEV_EMOJI.get(finding['severity'], '')} {index}. {finding['title']}**"
        )
        st.caption(
            f"Type: {_TYPE_LABELS.get(finding['type'], finding['type'])} "
            f"| Severity: {finding['severity'].upper()} "
            f"| Confidence: {finding['confidence']}"
        )
        st.write(finding["description"])
        config = finding.get("configuration_used", "").strip()
        if config and config.upper() != "N/A":
            st.markdown(f"**Configuration:** `{config}`")
        st.markdown(f"**Why it's a UX issue:** {finding['why_ux_issue']}")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**User impact:** {finding['user_impact']}")
        with col2:
            st.markdown(f"**Business impact:** {finding['business_impact']}")
        st.info(f"Suggestion: {finding['suggestion']}")


def build_copy_summary(result: Dict) -> str:
    lines = ["Findings:"]
    for f in result.get("findings", []):
        lines.append(f"- [{f['severity']}] ({f['type']}) {f['title']}")
    lines += ["", "Questions for PO:"]
    for q in result.get("questions_for_po", []):
        lines.append(f"- {q['question']}")
    return "\n".join(lines)


def build_copy_ui_summary(result: Dict) -> str:
    lines = [f"Flow: {result.get('flow_title', 'Untitled')}", ""]
    lines += ["Observed facts:"] + [f"- {i}" for i in result.get("observed_facts", [])]
    lines += ["", "High-level test cases:"] + [
        f"- {tc['title']}" for tc in result.get("high_level_test_cases", [])
    ]
    lines += ["", "Assumptions / unknowns:"] + [
        f"- {i}" for i in result.get("assumptions_and_unknowns", [])
    ]
    return "\n".join(lines)


def build_copy_ux_summary(result: Dict) -> str:
    a = result.get("overall_assessment", {})
    lines = [f"UX score: {a.get('feature_ux_score', '?')}/10", a.get("summary", ""), "", "Findings:"]
    for f in result.get("findings", []):
        lines.append(
            f"{_SEV_EMOJI.get(f['severity'], '')} [{f['severity'].upper()}] "
            f"({_TYPE_LABELS.get(f['type'], f['type'])}) {f['title']}"
        )
    return "\n".join(lines)


# ── Page config ──────────────────────────────────────────────────

st.set_page_config(page_title="QA Assistant", page_icon=None, layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
}

/* ── Layout ── */
.block-container {
    padding-top: 1.75rem;
    padding-bottom: 3rem;
    max-width: 1200px;
}

/* ── Headings ── */
h1 {
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    color: #0f172a !important;
    margin-bottom: 0 !important;
}
h2 {
    font-size: 1rem !important;
    font-weight: 600 !important;
    color: #1e293b !important;
    letter-spacing: -0.01em !important;
}
h3, h4 {
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    color: #334155 !important;
    letter-spacing: 0 !important;
}

p, li, .stMarkdown {
    font-size: 0.875rem !important;
    line-height: 1.6 !important;
    color: #334155;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #e2e8f0 !important;
    gap: 0 !important;
    padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    color: #64748b !important;
    padding: 0.625rem 1rem !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -1px !important;
    border-radius: 0 !important;
    letter-spacing: 0.01em;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #1e293b !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #1d4ed8 !important;
    border-bottom-color: #1d4ed8 !important;
    background: transparent !important;
    font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-border"] { display: none !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* ── Buttons ── */
div.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    height: 2.125rem !important;
    padding: 0 0.875rem !important;
    border-radius: 5px !important;
    border: 1px solid #cbd5e1 !important;
    color: #334155 !important;
    background: #ffffff !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    letter-spacing: 0.01em;
    transition: all 0.12s ease;
}
div.stButton > button:hover {
    border-color: #94a3b8 !important;
    background: #f8fafc !important;
    color: #1e293b !important;
}
div.stButton > button[kind="primary"],
div.stButton > button[kind="primary"] p,
div.stButton > button[kind="primary"] span,
div.stButton > button[kind="primary"] div {
    background: #1d4ed8 !important;
    color: #ffffff !important;
    border-color: #1d4ed8 !important;
    box-shadow: 0 1px 3px rgba(29,78,216,0.2) !important;
}
div.stButton > button[kind="primary"]:hover,
div.stButton > button[kind="primary"]:hover p,
div.stButton > button[kind="primary"]:hover span {
    background: #1e40af !important;
    border-color: #1e40af !important;
    color: #ffffff !important;
}
div.stButton > button[kind="primary"] * { color: #ffffff !important; }

/* ── Inputs ── */
textarea, input[type="text"], input[type="number"], input[type="email"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.875rem !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 5px !important;
    color: #1e293b !important;
}
textarea:focus, input:focus {
    border-color: #93c5fd !important;
    box-shadow: 0 0 0 3px rgba(147,197,253,0.2) !important;
}
textarea { line-height: 1.6 !important; }

/* ── Selectbox ── */
div[data-baseweb="select"] > div {
    font-size: 0.875rem !important;
    border-radius: 5px !important;
    border: 1px solid #e2e8f0 !important;
    font-family: 'Inter', sans-serif !important;
    background: #ffffff !important;
    min-height: 2.125rem !important;
    cursor: pointer !important;
}
div[data-baseweb="select"] > div:hover {
    border-color: #94a3b8 !important;
}
div[data-baseweb="select"] input {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    cursor: pointer !important;
}
div[data-baseweb="select"] [data-testid="stSelectboxLabel"],
div[data-baseweb="select"] span {
    font-size: 0.875rem !important;
    color: #1e293b !important;
}

/* Input labels */
label[data-testid="stWidgetLabel"] p {
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    color: #475569 !important;
}

/* ── Metric ── */
[data-testid="stMetric"] {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    padding: 0.875rem 1.125rem !important;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.6875rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: #64748b !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    letter-spacing: -0.02em !important;
}

/* ── Containers ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    padding: 0.875rem !important;
    background: #ffffff !important;
}

/* ── Alerts ── */
div[data-testid="stAlert"] {
    border-radius: 5px !important;
    font-size: 0.8125rem !important;
    padding: 0.625rem 0.875rem !important;
    border-width: 1px !important;
}
div[data-testid="stAlert"] p { font-size: 0.8125rem !important; }

/* ── Caption ── */
[data-testid="stCaptionContainer"] p {
    font-size: 0.75rem !important;
    color: #94a3b8 !important;
}

/* ── Expander ── */
details summary {
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    color: #475569 !important;
    padding: 0.5rem 0 !important;
}
details {
    border: 1px solid #f1f5f9 !important;
    border-radius: 5px !important;
    padding: 0 0.75rem !important;
    background: #fafafa !important;
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid #f1f5f9 !important;
    margin: 1.25rem 0 !important;
}

/* ── Code blocks ── */
pre {
    border-radius: 5px !important;
    font-size: 0.8125rem !important;
    border: 1px solid #e2e8f0 !important;
}

/* ── Success / info ── */
.stSuccess { border-left: 3px solid #10b981 !important; }
.stInfo    { border-left: 3px solid #3b82f6 !important; }
.stWarning { border-left: 3px solid #f59e0b !important; }
.stError   { border-left: 3px solid #ef4444 !important; }

/* ── Mode description ── */
.mode-desc {
    padding: 0.75rem 1rem;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    margin-bottom: 1.25rem;
    font-size: 0.8125rem;
    color: #475569;
    line-height: 1.6;
}

/* ── Spinner ── */
[data-testid="stSpinner"] p {
    font-size: 0.8125rem !important;
    color: #64748b !important;
}
</style>
""", unsafe_allow_html=True)


# ── Header ───────────────────────────────────────────────────────

col_title, col_project = st.columns([3, 1])
with col_title:
    st.title("QA Assistant")
    st.caption("Requirement analysis · Test case generation · UX review")

projects = get_project_dirs()
if not projects:
    st.error("No project folders found in ./projects")
    st.stop()

with col_project:
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    selected_project = st.selectbox(
        "Project",
        projects,
        help=(
            "Each project has its own context files (context.md, glossary.md, rules.md, "
            "product_context.md) that tell the AI about your product domain and review rules. "
            "Create a new folder under /projects/ to add a project."
        ),
    )
    project_data = load_project_context(selected_project)

st.markdown("---")


# ── Session state ────────────────────────────────────────────────

defaults = {
    "formatted_story_editor": "",
    "analysis_result": None,
    "ui_flow_result": None,
    "loaded_raw_text": "",
    "raw_story_input": "",
    "ui_observations_editor": "",
    "pending_ui_observations": None,
    "extracted_unknowns": [],
    "ux_result": None,
    "ux_observations_editor": "",
    "pending_ux_observations": None,
    "ux_extracted_unknowns": [],
    "ux_doc_results": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── OpenAI client ────────────────────────────────────────────────

try:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    if not api_key:
        st.error("OPENAI_API_KEY is not set. Add it to your .env file.")
        st.stop()
    client = OpenAI(api_key=api_key)
except Exception as exc:
    st.error(f"Failed to initialise OpenAI client: {exc}")
    st.stop()


# ── Tabs ─────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "Requirement Review",
    "Flow → Test Cases",
    "UX Review",
    "Project",
])


# ════════════════════════════════════════════════════════════════
# TAB 1 — Requirement review
# ════════════════════════════════════════════════════════════════
with tab1:
    st.markdown(
        '<div class="mode-desc">'
        "<b>When to use</b> you have a ticket, user story, or raw requirement text and want "
        "to find QA issues before development starts — missing definitions, contradictions, "
        "ambiguities, risks, and questions to ask the PO.<br>"
        "<b>How it works</b> paste or upload the raw text → format it into a structured story → "
        "run a two-pass AI review → get findings and PO questions."
        "</div>",
        unsafe_allow_html=True,
    )

    story_name = st.text_input(
        "Story name",
        value="adhoc_story",
        help="Used as the filename when saving the review output to /outputs/{project}/.",
    )

    col1, col2 = st.columns([1, 2])

    with col1:
        input_mode = st.radio(
            "Input mode",
            ["Paste raw text", "Upload file"],
            index=0,
            help="Choose how to provide the requirement. Both modes produce the same result.",
        )

        show_context = st.checkbox(
            "Show project context files",
            value=False,
            help="See what context the AI is using: scope, glossary, and review rules for this project.",
        )
        if show_context:
            with st.expander("context.md", expanded=False):
                st.code(project_data["context"], language="markdown")
            with st.expander("glossary.md", expanded=False):
                st.code(project_data["glossary"] or "— empty —", language="markdown")
            with st.expander("rules.md", expanded=False):
                st.code(project_data["rules"] or "— empty —", language="markdown")

    with col2:
        if input_mode == "Paste raw text":
            st.text_area(
                "Raw requirement",
                height=220,
                placeholder=(
                    "Paste the raw requirement, ticket description, or user story here.\n\n"
                    "It can be messy, informal, or incomplete — the formatter will structure it "
                    "while preserving all ambiguities. Don't clean it up before pasting."
                ),
                key="raw_story_input",
            )
        else:
            uploaded_file = st.file_uploader(
                "Upload .txt or .md file",
                type=["txt", "md"],
                help="Upload a plain text or Markdown file containing the requirement.",
            )
            if uploaded_file is not None:
                st.session_state.loaded_raw_text = uploaded_file.read().decode(
                    "utf-8", errors="ignore"
                )
            st.text_area(
                "Loaded file content",
                value=st.session_state.loaded_raw_text,
                height=220,
                disabled=True,
            )

        format_clicked = st.button(
            "Format story →",
            type="secondary",
            use_container_width=True,
            help=(
                "Structures the raw text into a standard story format (Feature, Actors, "
                "Main flow, Acceptance criteria, etc.) without improving or completing it. "
                "Review and edit the result before running the analysis."
            ),
        )

    if format_clicked:
        source_text = st.session_state.get(
            "raw_story_input" if input_mode == "Paste raw text" else "loaded_raw_text", ""
        ).strip()
        if not source_text:
            st.warning("Paste or upload a requirement first.")
            st.stop()
        try:
            with st.spinner("Formatting…"):
                draft_result = draft_story(
                    client=client,
                    model=model,
                    project_context=project_data["context"],
                    glossary=project_data["glossary"],
                    raw_story=source_text,
                )
            st.session_state.formatted_story_editor = draft_result.get("formatted_story", "")
        except Exception as exc:
            st.error(f"Formatting failed: {exc}")
            st.stop()

    st.divider()
    st.subheader("Formatted story")
    st.caption(
        "Review and edit before running the analysis. "
        "Fix obvious formatting issues, but keep ambiguities and missing information as-is — "
        "those are what the analysis should find."
    )

    formatted_story_value = st.text_area(
        "Formatted story (editable)",
        height=350,
        key="formatted_story_editor",
        label_visibility="collapsed",
    )

    analyze_clicked = st.button(
        "Analyze →",
        type="primary",
        use_container_width=True,
        help="Runs a two-pass AI review: first pass generates findings, second pass removes weak ones and sharpens the output.",
    )

    if analyze_clicked:
        if not formatted_story_value.strip():
            st.warning("Format or paste a story first.")
            st.stop()
        try:
            with st.spinner("Running two-pass review…"):
                result = review_requirement_two_pass(
                    client=client,
                    model=model,
                    project_context=project_data["context"],
                    glossary=project_data["glossary"],
                    rules=project_data["rules"],
                    story=formatted_story_value.strip(),
                )
            st.session_state.analysis_result = result
            output_path = save_ui_result(selected_project, story_name, result)
            st.success(f"Done. Saved to: {output_path}")
        except Exception as exc:
            st.error(f"Review failed: {exc}")
            st.stop()

    result = st.session_state.analysis_result
    if result:
        assessment = result["overall_assessment"]
        score = assessment["requirement_clarity_score"]

        st.subheader("Results")
        m_col, s_col = st.columns([1, 3])
        with m_col:
            st.metric("Clarity score", f"{score} / 10")
        with s_col:
            st.write(assessment["summary"])

        n = len(result.get("findings", []))
        if n <= 2:
            st.warning("Very few findings — the requirement may be clear, or the review filtered aggressively.")
        elif n <= 5:
            st.info("Finding count looks reasonable for a typical requirement.")
        else:
            st.info("Many findings — this may indicate a complex or ambiguous requirement.")

        sev_order = {"high": 0, "medium": 1, "low": 2}
        findings = sorted(
            result.get("findings", []),
            key=lambda x: (sev_order.get(x["severity"], 99), x["type"]),
        )
        questions = result.get("questions_for_po", [])

        st.subheader(f"Findings ({len(findings)})")
        for idx, f in enumerate(findings, 1):
            render_finding(f, idx)

        st.subheader(f"Questions for PO ({len(questions)})")
        for idx, q in enumerate(questions, 1):
            render_question(q, idx)

        with st.expander("Copy-ready summary"):
            st.code(build_copy_summary(result), language="text")
        with st.expander("Raw JSON"):
            st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")


# ════════════════════════════════════════════════════════════════
# TAB 2 — Flow → Test cases
# ════════════════════════════════════════════════════════════════
with tab2:
    st.markdown(
        '<div class="mode-desc">'
        "<b>When to use</b> you have screenshots of a UI flow and want to generate "
        "high-level test cases based on what's actually visible — not assumptions.<br>"
        "<b>How it works</b> upload screenshots → AI extracts observable facts → "
        "edit the facts → optionally add task text → generate test cases grounded in evidence."
        "</div>",
        unsafe_allow_html=True,
    )

    flow_name = st.text_input(
        "Flow name",
        value="adhoc_ui_flow",
        help="Used as the filename when saving the output to /outputs/{project}/.",
    )

    col1, col2 = st.columns([1, 2])

    with col1:
        uploaded_images = st.file_uploader(
            "Screenshots",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            help=(
                "Upload one or more screenshots of the UI flow you want to test. "
                "The AI will extract what it can see — fields, labels, buttons, states, "
                "error messages. You can edit the extracted facts before generating test cases."
            ),
        )

        extract_clicked = st.button(
            "Extract facts from screenshots",
            type="secondary",
            use_container_width=True,
            help="Sends all uploaded screenshots to the AI and extracts a list of observable UI facts. The result appears in the 'Observed facts' field on the right — review and edit it before generating test cases.",
        )

        show_context = st.checkbox(
            "Show project context",
            value=False,
            key="show_context_ui",
            help="See the context.md file the AI uses for this project.",
        )
        if show_context:
            with st.expander("context.md", expanded=False):
                st.code(project_data["context"], language="markdown")

    with col2:
        if st.session_state.pending_ui_observations is not None:
            st.session_state.ui_observations_editor = st.session_state.pending_ui_observations
            st.session_state.pending_ui_observations = None

        task_text = st.text_area(
            "Task text (optional)",
            height=120,
            placeholder=(
                "Paste the related ticket or requirement here if you have it.\n\n"
                "This gives the AI additional context about expected behavior. "
                "Leave empty if you only want test cases based on what's visible in the screenshots."
            ),
            help="Optional. If provided, the AI uses it alongside the observed facts to generate more targeted test cases.",
        )

        st.text_area(
            "Observed facts (editable)",
            height=260,
            key="ui_observations_editor",
            placeholder=(
                "After clicking 'Extract facts', the AI's observations appear here.\n"
                "You can also type them manually.\n\n"
                "Each line should be one concrete, visible fact:\n"
                "- Email field is visible and disabled\n"
                "- Save button is present and enabled\n"
                "- Error message 'Required field' appears under Password\n"
                "- User avatar shows initials 'AB' in top-right corner"
            ),
            help=(
                "These are the raw observations the test cases will be generated from. "
                "The more specific and accurate they are, the better the output. "
                "Remove anything you're not sure about — the AI should only test what's confirmed visible."
            ),
        )

        generate_clicked = st.button(
            "Generate test cases →",
            type="primary",
            use_container_width=True,
            help="Generates high-level test cases strictly grounded in the observed facts. Each test case includes a confidence level — low-confidence cases are based on inference and should be reviewed carefully.",
        )

    if st.session_state.extracted_unknowns:
        with st.expander("Unknowns from screenshot extraction", expanded=False):
            st.caption(
                "These elements were visible in the screenshots but their meaning or "
                "behavior was unclear. Review them — they may indicate missing context."
            )
            for item in st.session_state.extracted_unknowns:
                st.markdown(f"- {item}")

    if extract_clicked:
        if not uploaded_images:
            st.warning("Upload at least one screenshot first.")
            st.stop()
        try:
            with st.spinner("Extracting facts from screenshots…"):
                extract_result = extract_ui_observed_facts_from_images(
                    client=client,
                    model=model,
                    project_context=project_data["context"],
                    uploaded_files=uploaded_images,
                )
            st.session_state.pending_ui_observations = "\n".join(
                f"- {item}" for item in extract_result.get("observed_facts", [])
            )
            st.session_state.extracted_unknowns = extract_result.get("unknowns", [])
            st.rerun()
        except Exception as exc:
            st.error(f"Image extraction failed: {exc}")
            st.stop()

    if generate_clicked:
        observations_text = st.session_state.get("ui_observations_editor", "").strip()
        if not observations_text:
            st.warning("Add observed facts first — either extract them from screenshots or type them manually.")
            st.stop()
        try:
            with st.spinner("Generating test cases…"):
                result = generate_ui_flow_test_cases(
                    client=client,
                    model=model,
                    project_context=project_data["context"],
                    task_text=task_text.strip(),
                    ui_observations=observations_text,
                )
            st.session_state.ui_flow_result = result
            output_path = save_ui_result(selected_project, flow_name, result, suffix="_ui_flow")
            st.success(f"Done. Saved to: {output_path}")
        except Exception as exc:
            st.error(f"Generation failed: {exc}")
            st.stop()

    result = st.session_state.ui_flow_result
    if result:
        st.subheader(result.get("flow_title", "Results"))

        with st.expander("Observed facts used", expanded=False):
            for item in result.get("observed_facts", []):
                st.markdown(f"- {item}")

        test_cases = result.get("high_level_test_cases", [])
        st.markdown(f"### Test cases ({len(test_cases)})")
        st.caption(
            " High confidence = grounded in observations. "
            " Medium = minor inference. "
            " Low = mostly assumed — treat with caution."
        )
        for idx, tc in enumerate(test_cases, 1):
            render_test_case(tc, idx)

        unknowns = result.get("assumptions_and_unknowns", [])
        if unknowns:
            st.markdown("### Assumptions & unknowns")
            st.caption("These gaps could affect test coverage or expected results — worth clarifying with the team.")
            for item in unknowns:
                st.markdown(f"- {item}")

        with st.expander("Copy-ready summary"):
            st.code(build_copy_ui_summary(result), language="text")
        with st.expander("Raw JSON"):
            st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")


# ════════════════════════════════════════════════════════════════
# TAB 3 — UX / Feature review
# ════════════════════════════════════════════════════════════════
with tab3:
    st.markdown(
        '<div class="mode-desc">'
        "<b>When to use</b> you want to find UX issues, missing controls, and unserved "
        "business scenarios in a live product feature — without a spec document.<br>"
        "<b>How it works</b> set up product context → upload screenshots (optional) → "
        "add documentation URLs (optional) → describe the feature → run a two-pass UX analysis."
        "</div>",
        unsafe_allow_html=True,
    )

    flow_name = st.text_input(
        "Review name",
        value="adhoc_ux_review",
        help="Used as the filename when saving the output to /outputs/{project}/.",
    )

    product_context = project_data.get("product_context", "")
    has_product_context = bool(product_context.strip())

    col1, col2 = st.columns([1, 2])

    with col1:
        if has_product_context:
            st.success("product_context.md loaded")
            st.caption(
                "The AI has product background, target audience, and feature context. "
                "This significantly improves finding quality."
            )
        else:
            st.warning(
                "No product_context.md found for this project."
            )
            st.caption(
                "Add `projects/{project}/product_context.md` with product description, "
                "target audience, plan tiers, and feature details. "
                "See `projects/coupler_scheduler/` as a complete example."
            )

        st.markdown("**Screenshots** *(optional)*")
        uploaded_images = st.file_uploader(
            "Upload screenshots",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="ux_screenshots",
            label_visibility="collapsed",
            help=(
                "Upload screenshots of the feature you're reviewing. "
                "The AI will extract observable UI facts — what's visible, enabled, "
                "labeled, or missing. You can then edit the extracted facts before running the analysis."
            ),
        )

        extract_clicked = st.button(
            "Extract facts from screenshots",
            type="secondary",
            use_container_width=True,
            key="ux_extract_btn",
            help="Sends all uploaded screenshots to the AI. Extracted facts appear in the 'Observed UI facts' field on the right. Review and supplement them before running Analyze UX.",
        )

        st.markdown("**Documentation URLs** *(optional)*")
        st.caption(
            "Paste help center or docs URLs, one per line. "
            "The AI fetches them and uses the content to find gaps between "
            "documented behavior and what the UI communicates."
        )
        doc_urls_input = st.text_area(
            "Documentation URLs",
            height=100,
            placeholder=(
                "https://docs.example.com/feature/scheduler\n"
                "https://support.example.com/en/articles/limits"
            ),
            key="ux_doc_urls",
            label_visibility="collapsed",
        )

        fetch_docs_clicked = st.button(
            "Fetch documentation →",
            type="secondary",
            use_container_width=True,
            key="ux_fetch_docs_btn",
            help="Downloads the pages at the provided URLs and extracts readable text. This is especially useful for finding behaviors that are documented but not visible in the UI.",
        )

        doc_results = st.session_state.ux_doc_results
        if doc_results:
            for r in doc_results:
                if r.ok:
                    st.success(f" {(r.title or r.url)[:55]}")
                else:
                    st.error(f" {r.url[:55]}\n{r.error}")

        show_context = st.checkbox(
            "Show project context files",
            value=False,
            key="show_ctx_ux",
            help="Inspect all context files the AI uses for this project.",
        )
        if show_context:
            if has_product_context:
                with st.expander("product_context.md", expanded=False):
                    st.code(product_context, language="markdown")
            with st.expander("context.md", expanded=False):
                st.code(project_data["context"], language="markdown")
            if project_data.get("rules"):
                with st.expander("rules.md", expanded=False):
                    st.code(project_data["rules"], language="markdown")

    with col2:
        if st.session_state.pending_ux_observations is not None:
            st.session_state.ux_observations_editor = st.session_state.pending_ux_observations
            st.session_state.pending_ux_observations = None

        feature_description = st.text_area(
            "Feature description",
            height=120,
            placeholder=(
                "Describe the feature you're reviewing in a few sentences.\n\n"
                "Example:\n"
                "Reviewing the Automatic Data Refresh scheduler in Coupler.io — "
                "the interval selector, days-of-week picker, timezone dropdown, "
                "time preferences field, and toggle state behavior."
            ),
            key="ux_feature_description",
            help=(
                "Tell the AI what you're focusing on. Be specific about which part of the "
                "feature you're reviewing — this helps it generate targeted findings rather than "
                "generic UX observations."
            ),
        )

        st.text_area(
            "Observed UI facts *(editable)*",
            height=260,
            key="ux_observations_editor",
            placeholder=(
                "One observable fact per line. Click 'Extract facts' to auto-populate from screenshots,\n"
                "or type manually. Each fact should describe something concrete and visible.\n\n"
                "Good examples:\n"
                "- Toggle 'Automatic data refresh' is visible, currently ON\n"
                "- Interval dropdown shows: Every 15 min (locked), Every 30 min (locked), Every Hour, Daily, Monthly\n"
                "- Locked options show lock icon and 'Not in your plan' label, are non-clickable\n"
                "- Time preferences shows a range picker (09:00 → 18:00) for Every Hour\n"
                "- After saving, toast shows 'Schedule updated' — no next-run date shown"
            ),
            help=(
                "The AI uses these facts as its primary evidence source. "
                "More specific and accurate facts = better findings. "
                "Remove anything uncertain. Do NOT include interpretations — just what you see."
            ),
        )

        analyze_clicked = st.button(
            "Analyze UX →",
            type="primary",
            use_container_width=True,
            key="ux_analyze_btn",
            help="Runs a two-pass UX review using the feature description, observed facts, product context, and any fetched documentation. Pass 1 generates findings, pass 2 removes weak ones and sharpens the output.",
        )

    if st.session_state.ux_extracted_unknowns:
        with st.expander("Unknowns from screenshot extraction", expanded=False):
            st.caption(
                "Elements visible in screenshots but whose meaning or behavior is unclear. "
                "May indicate missing context worth investigating."
            )
            for item in st.session_state.ux_extracted_unknowns:
                st.markdown(f"- {item}")

    if any(r.ok for r in st.session_state.ux_doc_results):
        with st.expander("Documentation preview", expanded=False):
            for r in st.session_state.ux_doc_results:
                if r.ok:
                    st.markdown(f"**{r.title or r.url}** — `{r.url}`")
                    if r.truncated:
                        st.caption(f"Truncated to {r.chars:,} characters")
                    st.code(
                        r.text[:2000] + ("…" if len(r.text) > 2000 else ""),
                        language="text",
                    )

    if fetch_docs_clicked:
        urls = [u.strip() for u in st.session_state.get("ux_doc_urls", "").splitlines() if u.strip()]
        if not urls:
            st.warning("Enter at least one URL first.")
            st.stop()
        with st.spinner(f"Fetching {len(urls)} page(s)…"):
            results = fetch_urls(urls)
        st.session_state.ux_doc_results = results
        ok = sum(1 for r in results if r.ok)
        fail = len(results) - ok
        if ok:
            st.success(f"Fetched {ok} page(s) successfully.")
        if fail:
            st.warning(f"{fail} URL(s) could not be fetched.")
        st.rerun()

    if extract_clicked:
        if not uploaded_images:
            st.warning("Upload at least one screenshot first.")
            st.stop()
        try:
            with st.spinner("Extracting facts from screenshots…"):
                extract_result = extract_ui_observed_facts_from_images(
                    client=client,
                    model=model,
                    project_context=project_data["context"],
                    uploaded_files=uploaded_images,
                )
            st.session_state.pending_ux_observations = "\n".join(
                f"- {item}" for item in extract_result.get("observed_facts", [])
            )
            st.session_state.ux_extracted_unknowns = extract_result.get("unknowns", [])
            st.rerun()
        except Exception as exc:
            st.error(f"Screenshot extraction failed: {exc}")
            st.stop()

    if analyze_clicked:
        observations = st.session_state.get("ux_observations_editor", "").strip()
        description = st.session_state.get("ux_feature_description", "").strip()
        if not observations and not description:
            st.warning("Add at least a feature description or some observed facts.")
            st.stop()
        try:
            with st.spinner("Running two-pass UX analysis…"):
                doc_context = results_to_context(st.session_state.ux_doc_results)
                result = review_ux_feature(
                    client=client,
                    model=model,
                    product_context=product_context,
                    feature_description=description,
                    ui_observations=observations,
                    documentation_context=doc_context,
                )
            st.session_state.ux_result = result
            output_path = save_ui_result(selected_project, flow_name, result, suffix="_ux")
            st.success(f"Done. Saved to: {output_path}")
        except Exception as exc:
            st.error(f"UX review failed: {exc}")
            st.stop()

    result = st.session_state.ux_result
    if result:
        assessment = result.get("overall_assessment", {})
        score = assessment.get("feature_ux_score")
        summary = assessment.get("summary", "")

        st.subheader("Results")
        m_col, s_col = st.columns([1, 3])
        with m_col:
            st.metric("UX score", f"{score} / 10")
        with s_col:
            st.write(summary)

        findings = result.get("findings", [])
        _sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings_sorted = sorted(
            findings,
            key=lambda x: (_sev_order.get(x["severity"], 99), x["type"]),
        )

        if findings_sorted:
            counts: Dict[str, int] = {}
            for f in findings_sorted:
                counts[f["severity"]] = counts.get(f["severity"], 0) + 1
            stat_cols = st.columns(len(counts))
            for col, (sev, cnt) in zip(
                stat_cols,
                sorted(counts.items(), key=lambda x: _sev_order.get(x[0], 99)),
            ):
                col.metric(f"{_SEV_EMOJI.get(sev, '')} {sev.capitalize()}", cnt)

        st.subheader(f"Findings ({len(findings_sorted)})")
        for idx, f in enumerate(findings_sorted, 1):
            render_ux_finding(f, idx)

        with st.expander("Copy-ready summary"):
            st.code(build_copy_ux_summary(result), language="text")
        with st.expander("Raw JSON"):
            st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")


# ════════════════════════════════════════════════════════════════
# TAB 4 — Project editor
# ════════════════════════════════════════════════════════════════
with tab4:
    st.markdown(
        '<div class="mode-desc">'
        "<b>Manage project context files.</b> "
        "These files tell the AI about your product, domain rules, and review scope. "
        "Better context = more relevant findings. Changes are saved to disk immediately "
        "and take effect on the next analysis run."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Project files config ─────────────────────────────────────
    PROJECT_FILES = [
        {
            "key": "context",
            "filename": "context.md",
            "label": "Scope — context.md",
            "required": True,
            "height": 220,
            "description": (
                "**Required for all modes.** "
                "Defines what is and isn't being reviewed in this project. "
                "Helps the AI stay focused on the relevant area."
            ),
            "placeholder": (
                "# Project: My Product\n\n"
                "## Scope\nThis project covers the checkout flow in MyApp.\n\n"
                "## What we are reviewing\n- Payment form\n- Order confirmation screen\n\n"
                "## Out of scope\n- Account settings\n- Admin panel"
            ),
        },
        {
            "key": "product_context",
            "filename": "product_context.md",
            "label": "Product context — product_context.md",
            "required": False,
            "height": 320,
            "description": (
                "**Required for UX / Feature review mode.** "
                "Describes the product, target audience, business model, and the specific "
                "feature being analysed. The richer this file, the more accurate the UX findings."
            ),
            "placeholder": (
                "# Product: MyApp\n\n"
                "## What it does\nMyApp is a SaaS tool for...\n\n"
                "## Target audience\nNon-technical marketing teams at mid-size companies.\n\n"
                "## Business model\nSubscription — Free / Pro ($29/mo) / Business ($99/mo)\n\n"
                "## Feature under analysis: Checkout flow\n\n"
                "### Purpose\n...\n\n"
                "### Where it lives\n...\n\n"
                "### Key user goals\n1. ...\n2. ..."
            ),
        },
        {
            "key": "glossary",
            "filename": "glossary.md",
            "label": "Glossary — glossary.md",
            "required": False,
            "height": 200,
            "description": (
                "**Optional.** "
                "Product-specific terms the AI should use consistently in findings. "
                "Helps avoid terminology mismatches between the AI output and your team's language."
            ),
            "placeholder": (
                "# Glossary\n\n"
                "- **Flow:** a configured data pipeline\n"
                "- **Run:** a single execution of a flow\n"
                "- Use 'flow', not 'pipeline' or 'job'"
            ),
        },
        {
            "key": "rules",
            "filename": "rules.md",
            "label": "Review rules — rules.md",
            "required": False,
            "height": 220,
            "description": (
                "**Optional.** "
                "Controls what the AI focuses on and what it should deprioritise. "
                "Add priority rules, evidence requirements, or findings to suppress."
            ),
            "placeholder": (
                "# Review rules\n\n"
                "## Prioritise\n1. Silent failures\n2. Missing feedback on destructive actions\n\n"
                "## Deprioritise\n- Copy / wording improvements\n- Generic tooltip suggestions\n\n"
                "## Evidence requirement\nEvery finding must cite a specific observed fact."
            ),
        },
    ]

    project_root = Path("projects") / selected_project

    # ── Create new project ───────────────────────────────────────
    with st.expander("Create a new project", expanded=False):
        st.caption(
            "Creates a new project folder with empty context files. "
            "Fill in the files after creation, then select the project from the dropdown at the top."
        )
        new_name_col, new_btn_col = st.columns([3, 1])
        with new_name_col:
            new_project_name = st.text_input(
                "Project name",
                placeholder="e.g. my_product_checkout",
                label_visibility="collapsed",
                key="new_project_name_input",
                help="Use lowercase letters, numbers, and underscores. No spaces.",
            )
        with new_btn_col:
            create_project_clicked = st.button(
                "Create",
                type="secondary",
                use_container_width=True,
                key="create_project_btn",
            )

        if create_project_clicked:
            raw = new_project_name.strip()
            safe = "".join(c if c.isalnum() or c == "_" else "_" for c in raw).strip("_")
            if not safe:
                st.error("Enter a valid project name.")
            elif (Path("projects") / safe).exists():
                st.warning(f"Project '{safe}' already exists.")
            else:
                new_dir = Path("projects") / safe
                new_dir.mkdir(parents=True)
                (new_dir / "context.md").write_text(
                    f"# Project: {safe}\n\n## Scope\n\n## Out of scope\n",
                    encoding="utf-8",
                )
                for fname in ("glossary.md", "rules.md", "product_context.md"):
                    (new_dir / fname).write_text("", encoding="utf-8")
                st.success(
                    f"Project '{safe}' created. Select it from the Project dropdown at the top."
                )
                st.rerun()

    st.markdown("---")
    st.subheader(f"Editing: {selected_project}")

    # ── File editors ─────────────────────────────────────────────
    for file_cfg in PROJECT_FILES:
        file_path = project_root / file_cfg["filename"]
        file_key = file_cfg["key"]
        editor_key = f"proj_editor_{selected_project}_{file_key}"

        # Load current content from disk on first render or after project change
        disk_content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""

        # Initialise session state from disk if not yet set for this project
        state_key = f"proj_content_{selected_project}_{file_key}"
        if state_key not in st.session_state:
            st.session_state[state_key] = disk_content

        st.markdown(f"#### {file_cfg['label']}")
        st.markdown(
            file_cfg["description"]
            + (" *(required)*" if file_cfg["required"] else " *(optional)*")
        )

        edited_content = st.text_area(
            file_cfg["label"],
            value=st.session_state[state_key],
            height=file_cfg["height"],
            placeholder=file_cfg["placeholder"],
            key=editor_key,
            label_visibility="collapsed",
        )

        save_col, status_col = st.columns([1, 4])
        with save_col:
            save_clicked = st.button(
                "Save",
                key=f"save_{selected_project}_{file_key}",
                type="secondary",
                use_container_width=True,
            )

        if save_clicked:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(edited_content, encoding="utf-8")
            st.session_state[state_key] = edited_content
            with status_col:
                st.success(f"Saved {file_cfg['filename']}")

        st.markdown("")
