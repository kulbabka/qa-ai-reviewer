import json
import os
import datetime
from pathlib import Path
from typing import Dict, List, Optional

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


def list_output_files(project_name: str, suffix: str = "") -> List[Path]:
    """List saved AI-review output JSON files for a project, newest first.

    If `suffix` is given (e.g. "_ux", "_ui_flow"), only files whose stem
    ends with that suffix are returned — used to separate Screen Review
    outputs (test cases vs UX findings) from Requirement Review outputs.

    quick_notes.json is always excluded — it's a manual note list, not an
    AI review result, and would never load successfully here.
    """
    output_dir = Path("outputs") / project_name
    if not output_dir.exists():
        return []
    files = [
        p for p in output_dir.glob("*.json")
        if p.name != "quick_notes.json" and (not suffix or p.stem.endswith(suffix))
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def render_load_last_result(project_name: str, suffix: str, widget_key: str) -> Optional[Dict]:
    """Render a 'Saved results' manager: lists every saved output for this
    project (optionally filtered by suffix), with a Load and a Delete
    button per item. Returns the loaded dict if the caller should apply it
    this run, or None otherwise.

    This does NOT touch session_state for the loaded content itself — the
    caller decides where the loaded result goes, since different tabs store
    results under different keys. Deletion is handled internally (removes
    the file from disk and reruns).
    """
    files = list_output_files(project_name, suffix)
    if not files:
        return None

    with st.expander(f"Saved results ({len(files)})", expanded=False):
        st.caption(
            "Everything saved to disk for this project. Load brings a result "
            "back into the view above; Delete removes it permanently from disk."
        )
        for path in files:
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = path.stat().st_size / 1024
            row = st.container(border=True)
            with row:
                name_col, load_col, del_col = st.columns([4, 1, 1])
                with name_col:
                    st.markdown(f"**{path.name}**")
                    st.caption(f"{mtime} · {size_kb:.1f} KB")
                with load_col:
                    load_clicked = st.button(
                        "Load", key=f"{widget_key}_load_{path.name}",
                        use_container_width=True,
                    )
                with del_col:
                    delete_clicked = st.button(
                        "Delete", key=f"{widget_key}_del_{path.name}",
                        use_container_width=True,
                    )
                if load_clicked:
                    try:
                        return json.loads(path.read_text(encoding="utf-8"))
                    except Exception as exc:
                        st.error(f"Could not load {path.name}: {exc}")
                        return None
                if delete_clicked:
                    try:
                        path.unlink()
                        st.success(f"Deleted {path.name}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not delete {path.name}: {exc}")
    return None


def get_quick_notes_path(project_name: str) -> Path:
    return Path("outputs") / project_name / "quick_notes.json"


def load_quick_notes(project_name: str) -> List[Dict]:
    path = get_quick_notes_path(project_name)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_quick_notes(project_name: str, notes: List[Dict]) -> None:
    path = get_quick_notes_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


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
    st.caption("Screen review (test cases / UX) · Requirement analysis · Quick notes")

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
    # Requirement Review
    "formatted_story_editor": "",
    "analysis_result": None,
    "loaded_raw_text": "",
    "raw_story_input": "",
    # Screen Review (merged Test Cases / UX Findings)
    "screen_result": None,
    "screen_result_kind": None,  # "test_cases" | "ux_findings"
    "screen_observations_editor": "",
    "pending_screen_observations": None,
    "screen_extracted_unknowns": [],
    "screen_doc_results": [],
    # Quick Notes
    "quick_notes_list": [],
    "quick_notes_project": None,
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

tab_screen, tab_req, tab_notes, tab_proj = st.tabs([
    "Screen Review",
    "Requirement Review",
    "Quick Notes",
    "Project",
])


# ════════════════════════════════════════════════════════════════
# TAB — Screen Review (merged: Flow → Test Cases + UX Review)
# ════════════════════════════════════════════════════════════════
with tab_screen:
    st.markdown(
        '<div class="mode-desc">'
        "<b>When to use</b> you have a live screen or screenshots and want either "
        "grounded test cases or a structured UX review — pick the output style below.<br>"
        "<b>How it works</b> upload screenshots and/or describe the screen → AI extracts "
        "observable facts → edit them → generate either high-level test cases or "
        "UX findings (silent failure, ambiguous state, missing feedback, plan gate UX, etc.), "
        "grounded in your project's context, glossary, and rules."
        "</div>",
        unsafe_allow_html=True,
    )

    output_style = st.radio(
        "Output style",
        ["UX findings", "Test cases"],
        index=0,
        horizontal=True,
        key="screen_output_style",
        help=(
            "UX findings: structured findings with severity, user/business impact, "
            "and a fix suggestion — best when the task is about UX quality. "
            "Test cases: plain high-level test cases with steps and expected results — "
            "best when the task is 'write test cases for this'."
        ),
    )
    is_ux_mode = output_style == "UX findings"

    review_name = st.text_input(
        "Review name",
        value="adhoc_screen_review",
        help="Used as the filename when saving the output to /outputs/{project}/.",
    )

    product_context = project_data.get("product_context", "")
    has_product_context = bool(product_context.strip())

    col1, col2 = st.columns([1, 2])

    with col1:
        if has_product_context:
            st.success("product_context.md loaded")
        else:
            st.warning(
                "No product_context.md for this project — findings will rely on "
                "context.md only. Recommended for UX findings mode; see the "
                "Project tab to add it."
            )

        st.markdown("**Screenshots** *(optional)*")
        uploaded_images = st.file_uploader(
            "Upload screenshots",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="screen_screenshots",
            label_visibility="collapsed",
            help=(
                "Upload screenshots of the screen/flow you're reviewing. "
                "The AI extracts observable UI facts — what's visible, enabled, "
                "labeled, or missing. Review and edit before generating output."
            ),
        )

        extract_clicked = st.button(
            "Extract facts from screenshots",
            type="secondary",
            use_container_width=True,
            key="screen_extract_btn",
            help="Sends all uploaded screenshots to the AI and populates 'Observed facts' on the right.",
        )

        st.markdown("**Documentation URLs** *(optional)*")
        st.caption(
            "Paste help center or docs URLs, one per line. Used to find gaps "
            "between documented behavior and what the UI communicates "
            "(UX findings mode), or folded into context for test case generation."
        )
        doc_urls_input = st.text_area(
            "Documentation URLs",
            height=90,
            placeholder=(
                "https://docs.example.com/feature/scheduler\n"
                "https://support.example.com/en/articles/limits"
            ),
            key="screen_doc_urls",
            label_visibility="collapsed",
        )

        fetch_docs_clicked = st.button(
            "Fetch documentation →",
            type="secondary",
            use_container_width=True,
            key="screen_fetch_docs_btn",
            help="Downloads the pages at the provided URLs and extracts readable text.",
        )

        doc_results = st.session_state.screen_doc_results
        if doc_results:
            for r in doc_results:
                if r.ok:
                    st.success(f" {(r.title or r.url)[:55]}")
                else:
                    st.error(f" {r.url[:55]}\n{r.error}")

        show_context = st.checkbox(
            "Show project context files",
            value=False,
            key="show_ctx_screen",
            help="Inspect all context files the AI uses for this project.",
        )
        if show_context:
            if has_product_context:
                with st.expander("product_context.md", expanded=False):
                    st.code(product_context, language="markdown")
            with st.expander("context.md", expanded=False):
                st.code(project_data["context"], language="markdown")
            if project_data.get("glossary"):
                with st.expander("glossary.md", expanded=False):
                    st.code(project_data["glossary"], language="markdown")
            if project_data.get("rules"):
                with st.expander("rules.md", expanded=False):
                    st.code(project_data["rules"], language="markdown")

        loaded = render_load_last_result(
            selected_project, suffix="", widget_key="load_screen_result"
        )
        if loaded is not None:
            if "feature_ux_score" in loaded.get("overall_assessment", {}):
                st.session_state.screen_result = loaded
                st.session_state.screen_result_kind = "ux_findings"
                st.success("Loaded previous result below.")
            elif "high_level_test_cases" in loaded:
                st.session_state.screen_result = loaded
                st.session_state.screen_result_kind = "test_cases"
                st.success("Loaded previous result below.")
            else:
                st.warning("That file doesn't look like a Screen Review result — pick a different one.")

    with col2:
        if st.session_state.pending_screen_observations is not None:
            st.session_state.screen_observations_editor = st.session_state.pending_screen_observations
            st.session_state.pending_screen_observations = None

        feature_description = st.text_area(
            "Task / feature description",
            height=120,
            placeholder=(
                "Describe what you're reviewing or the task you were given.\n\n"
                "Example: \"Review the Broker Sync status area — the connection "
                "indicator, last-sync timestamp, and error state when a sync fails.\""
            ),
            key="screen_feature_description",
            help="Tell the AI what you're focusing on — this produces more targeted output than a generic pass.",
        )

        st.text_area(
            "Observed facts *(editable)*",
            height=260,
            key="screen_observations_editor",
            placeholder=(
                "One observable fact per line. Click 'Extract facts' to auto-populate "
                "from screenshots, or type manually while looking at a live screen.\n\n"
                "Good examples:\n"
                "- Broker Sync status shows a green dot and 'Connected' label\n"
                "- Last sync timestamp reads '2 minutes ago'\n"
                "- No visible indicator for a failed/paused sync state\n"
                "- Manual 'Sync now' button is present and enabled"
            ),
            help=(
                "The AI uses these facts as its primary evidence source. "
                "Remove anything uncertain — only include what's actually confirmed visible."
            ),
        )

        analyze_clicked = st.button(
            "Analyze UX →" if is_ux_mode else "Generate test cases →",
            type="primary",
            use_container_width=True,
            key="screen_analyze_btn",
            help=(
                "Runs a two-pass UX review grounded in observed facts, product context, "
                "documentation, and rules.md priorities."
                if is_ux_mode else
                "Generates high-level test cases grounded in observed facts, context, "
                "glossary, and rules.md priorities."
            ),
        )

    if st.session_state.screen_extracted_unknowns:
        with st.expander("Unknowns from screenshot extraction", expanded=False):
            st.caption(
                "Elements visible in screenshots but whose meaning or behavior is "
                "unclear. May indicate missing context worth investigating."
            )
            for item in st.session_state.screen_extracted_unknowns:
                st.markdown(f"- {item}")

    if any(r.ok for r in st.session_state.screen_doc_results):
        with st.expander("Documentation preview", expanded=False):
            for r in st.session_state.screen_doc_results:
                if r.ok:
                    st.markdown(f"**{r.title or r.url}** — `{r.url}`")
                    if r.truncated:
                        st.caption(f"Truncated to {r.chars:,} characters")
                    st.code(
                        r.text[:2000] + ("…" if len(r.text) > 2000 else ""),
                        language="text",
                    )

    if fetch_docs_clicked:
        urls = [u.strip() for u in st.session_state.get("screen_doc_urls", "").splitlines() if u.strip()]
        if not urls:
            st.warning("Enter at least one URL first.")
            st.stop()
        with st.spinner(f"Fetching {len(urls)} page(s)…"):
            results = fetch_urls(urls)
        st.session_state.screen_doc_results = results
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
            st.session_state.pending_screen_observations = "\n".join(
                f"- {item}" for item in extract_result.get("observed_facts", [])
            )
            st.session_state.screen_extracted_unknowns = extract_result.get("unknowns", [])
            st.rerun()
        except Exception as exc:
            st.error(f"Screenshot extraction failed: {exc}")
            st.stop()

    if analyze_clicked:
        observations = st.session_state.get("screen_observations_editor", "").strip()
        description = st.session_state.get("screen_feature_description", "").strip()
        if not observations and not description:
            st.warning("Add at least a task/feature description or some observed facts.")
            st.stop()
        try:
            if is_ux_mode:
                with st.spinner("Running two-pass UX analysis…"):
                    doc_context = results_to_context(st.session_state.screen_doc_results)
                    result = review_ux_feature(
                        client=client,
                        model=model,
                        product_context=product_context,
                        feature_description=description,
                        ui_observations=observations,
                        documentation_context=doc_context,
                        rules=project_data.get("rules", ""),
                    )
                st.session_state.screen_result = result
                st.session_state.screen_result_kind = "ux_findings"
                output_path = save_ui_result(selected_project, review_name, result, suffix="_ux")
            else:
                doc_context = results_to_context(st.session_state.screen_doc_results)
                task_text = description
                if doc_context.strip():
                    task_text = f"{description}\n\nDocumentation:\n{doc_context}".strip()
                with st.spinner("Generating test cases…"):
                    result = generate_ui_flow_test_cases(
                        client=client,
                        model=model,
                        project_context=project_data["context"],
                        task_text=task_text,
                        ui_observations=observations,
                        glossary=project_data.get("glossary", ""),
                        rules=project_data.get("rules", ""),
                        product_context=product_context,
                    )
                st.session_state.screen_result = result
                st.session_state.screen_result_kind = "test_cases"
                output_path = save_ui_result(selected_project, review_name, result, suffix="_ui_flow")
            st.success(f"Done. Saved to: {output_path}")
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            st.stop()

    result = st.session_state.screen_result
    kind = st.session_state.screen_result_kind
    if result and kind == "ux_findings":
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

    elif result and kind == "test_cases":
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
# TAB — Requirement review
# ════════════════════════════════════════════════════════════════
with tab_req:
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

        loaded = render_load_last_result(
            selected_project, suffix="", widget_key="load_req_result"
        )
        if loaded is not None and "overall_assessment" in loaded and "requirement_clarity_score" in loaded.get("overall_assessment", {}):
            st.session_state.analysis_result = loaded
            st.success("Loaded previous result below.")
        elif loaded is not None:
            st.warning("That file doesn't look like a Requirement Review result — pick a different one.")

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
# TAB — Quick Notes (no AI call — instant capture, works offline)
# ════════════════════════════════════════════════════════════════
with tab_notes:
    st.markdown(
        '<div class="mode-desc">'
        "<b>When to use</b> you need to capture a finding right now — no AI call, no waiting "
        "on network/API latency. Good for live sessions when every second counts.<br>"
        "<b>How it works</b> fill in the structured fields → Add note → copy individual notes "
        "or the full list from the code blocks below (hover for the copy icon). "
        "Notes are saved to disk automatically, per project."
        "</div>",
        unsafe_allow_html=True,
    )

    # Load this project's notes from disk the first time we see it (or on project switch)
    if st.session_state.quick_notes_project != selected_project:
        st.session_state.quick_notes_list = load_quick_notes(selected_project)
        st.session_state.quick_notes_project = selected_project

    # ── Import / Export ─────────────────────────────────────────
    exp_col, imp_col = st.columns(2)

    with exp_col:
        if st.session_state.quick_notes_list:
            st.download_button(
                "Download notes (JSON)",
                data=json.dumps(st.session_state.quick_notes_list, ensure_ascii=False, indent=2),
                file_name=f"{selected_project}_quick_notes.json",
                mime="application/json",
                use_container_width=True,
            )
        else:
            st.button("Download notes (JSON)", disabled=True, use_container_width=True,
                       help="Add at least one note first.")

    with imp_col:
        import_open = st.button("Import notes ↓", use_container_width=True, key="open_import_notes")

    if import_open:
        st.session_state["_show_import_notes"] = not st.session_state.get("_show_import_notes", False)

    if st.session_state.get("_show_import_notes", False):
        with st.container(border=True):
            st.caption(
                "Bring in notes prepared earlier — e.g. a findings library you drafted "
                "with Claude before the call. Paste JSON (a list of note objects) or "
                "plain text (one Given/When/Then-style block per note, separated by "
                "blank lines)."
            )
            import_mode = st.radio(
                "Import as",
                ["JSON", "Plain text"],
                horizontal=True,
                key="import_notes_mode",
                label_visibility="collapsed",
            )
            uploaded_notes_file = st.file_uploader(
                "Or upload a .json/.txt file instead",
                type=["json", "txt", "md"],
                key="import_notes_file",
            )
            import_text = st.text_area(
                "Paste content",
                height=180,
                key="import_notes_text",
                placeholder=(
                    '[{"title": "...", "severity": "High", "given": "...", "when": "...", '
                    '"then_expected": "...", "actual": "...", "environment": "", "extra_notes": ""}]'
                    if import_mode == "JSON" else
                    "Title: Sync status shows Connected during active failure\n"
                    "Severity: High\n"
                    "Given: Broker is connected and syncing normally\n"
                    "When: Broker connection drops mid-sync\n"
                    "Then (expected): UI shows a clear 'Sync failed' state\n"
                    "Actual: Status still shows green 'Connected'\n"
                    "\n"
                    "Title: Next note...\n..."
                ),
            )

            do_import = st.button("Add these to my notes", type="primary", use_container_width=True)

            if do_import:
                raw = (uploaded_notes_file.read().decode("utf-8", errors="ignore")
                       if uploaded_notes_file is not None else import_text)
                if not raw.strip():
                    st.warning("Paste some content or upload a file first.")
                else:
                    try:
                        if import_mode == "JSON":
                            parsed = json.loads(raw)
                            if isinstance(parsed, dict):
                                parsed = [parsed]
                            new_notes = []
                            for item in parsed:
                                new_notes.append({
                                    "title": str(item.get("title", "Untitled")),
                                    "severity": str(item.get("severity", "Medium")),
                                    "environment": str(item.get("environment", "")),
                                    "given": str(item.get("given", "")),
                                    "when": str(item.get("when", "")),
                                    "then_expected": str(item.get("then_expected", item.get("then", ""))),
                                    "actual": str(item.get("actual", "")),
                                    "extra_notes": str(item.get("extra_notes", item.get("notes", ""))),
                                })
                        else:
                            # Plain text: split into blocks on blank lines, parse "Label: value" lines
                            field_map = {
                                "title": "title", "severity": "severity", "environment": "environment",
                                "given": "given", "when": "when",
                                "then (expected)": "then_expected", "then": "then_expected",
                                "actual": "actual", "notes": "extra_notes",
                            }
                            blocks = [b for b in raw.split("\n\n") if b.strip()]
                            new_notes = []
                            for block in blocks:
                                note = {"title": "Untitled", "severity": "Medium", "environment": "",
                                        "given": "", "when": "", "then_expected": "", "actual": "", "extra_notes": ""}
                                for line in block.splitlines():
                                    if ":" not in line:
                                        continue
                                    label, _, value = line.partition(":")
                                    key = field_map.get(label.strip().lower())
                                    if key:
                                        note[key] = value.strip()
                                if note["title"] != "Untitled" or note["given"] or note["when"]:
                                    new_notes.append(note)
                        if not new_notes:
                            st.warning("Nothing recognizable to import — check the format.")
                        else:
                            st.session_state.quick_notes_list.extend(new_notes)
                            save_quick_notes(selected_project, st.session_state.quick_notes_list)
                            st.session_state["_show_import_notes"] = False
                            st.success(f"Imported {len(new_notes)} note(s).")
                            st.rerun()
                    except json.JSONDecodeError as exc:
                        st.error(f"Couldn't parse JSON: {exc}")
                    except Exception as exc:
                        st.error(f"Import failed: {exc}")

    with st.form("quick_note_form", clear_on_submit=True):
        title = st.text_input(
            "Title",
            placeholder="Short name for this finding, e.g. 'Sync status shows Connected during active failure'",
        )
        sev_col, env_col = st.columns(2)
        with sev_col:
            severity = st.selectbox("Severity", ["Critical", "High", "Medium", "Low"], index=2)
        with env_col:
            environment = st.text_input("Environment (optional)", placeholder="staging, Chrome, account: demo")

        given = st.text_area("Given (starting state)", height=70, placeholder="Broker is connected and syncing normally")
        when = st.text_area("When (action / trigger)", height=70, placeholder="Broker connection drops mid-sync")
        then_expected = st.text_area("Then — expected", height=70, placeholder="UI shows a clear 'Sync failed' state with a retry option")
        actual = st.text_area("Actual result", height=70, placeholder="Status still shows green 'Connected', no error surfaced")
        extra_notes = st.text_area("Additional notes (optional)", height=60, placeholder="Repro rate, screenshots taken, related findings...")

        submitted = st.form_submit_button("Add note", type="primary", use_container_width=True)

    if submitted:
        if not title.strip():
            st.warning("Add a title before saving the note.")
        else:
            st.session_state.quick_notes_list.append({
                "title": title.strip(),
                "severity": severity,
                "environment": environment.strip(),
                "given": given.strip(),
                "when": when.strip(),
                "then_expected": then_expected.strip(),
                "actual": actual.strip(),
                "extra_notes": extra_notes.strip(),
            })
            save_quick_notes(selected_project, st.session_state.quick_notes_list)
            st.success(f"Added and saved: {title.strip()}")

    notes = st.session_state.quick_notes_list

    if notes:
        st.divider()
        st.subheader(f"Notes ({len(notes)})")
        st.caption(f"Auto-saved to `{get_quick_notes_path(selected_project)}`")

        clear_col, _ = st.columns([1, 4])
        with clear_col:
            if st.button("Clear all", use_container_width=True):
                st.session_state.quick_notes_list = []
                save_quick_notes(selected_project, [])
                st.rerun()

        def _format_note(n: Dict, idx: int) -> str:
            lines = [f"{idx}. [{n['severity']}] {n['title']}"]
            if n["environment"]:
                lines.append(f"Environment: {n['environment']}")
            if n["given"]:
                lines.append(f"Given: {n['given']}")
            if n["when"]:
                lines.append(f"When: {n['when']}")
            if n["then_expected"]:
                lines.append(f"Then (expected): {n['then_expected']}")
            if n["actual"]:
                lines.append(f"Actual: {n['actual']}")
            if n["extra_notes"]:
                lines.append(f"Notes: {n['extra_notes']}")
            return "\n".join(lines)

        for idx, n in enumerate(notes, 1):
            with st.container(border=True):
                st.markdown(f"**{idx}. [{n['severity']}] {n['title']}**")
                st.code(_format_note(n, idx), language="text")

        with st.expander("Copy all notes as one block", expanded=False):
            all_text = "\n\n".join(_format_note(n, i) for i, n in enumerate(notes, 1))
            st.code(all_text, language="text")
    else:
        st.caption("No notes yet — fill in the form above to add the first one.")


# ════════════════════════════════════════════════════════════════
# TAB — Project editor
# ════════════════════════════════════════════════════════════════
with tab_proj:
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
                "**Used by Screen Review (both output styles) and Requirement Review.** "
                "Describes the product, target audience, business model, and the specific "
                "feature being analysed. The richer this file, the more accurate the findings."
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
                "**Optional, used by all modes.** "
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
                "**Optional, used by all modes.** "
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
