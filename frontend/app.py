import os
from pathlib import Path
from uuid import uuid4
from typing import Any

import requests
import streamlit as st

from services.pipeline import run_pipeline


API_BASE_URL = os.getenv("ASSESSMENT_API_URL", "http://127.0.0.1:8000").rstrip("/")
ROOT_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT_DIR / "storage" / "uploads"
OUTPUT_DIR = ROOT_DIR / "storage" / "outputs"
REQUEST_CONNECT_TIMEOUT = int(os.getenv("ASSESSMENT_API_CONNECT_TIMEOUT", "2"))
REQUEST_READ_TIMEOUT = int(os.getenv("ASSESSMENT_API_READ_TIMEOUT", "600"))
DEFAULT_REVIEW_ENGINE_LABEL = "Local fallback review"
REVIEW_ENGINE_OPTIONS = {
    "Fast assessor (recommended)": "local",
    "Claude assessor (slower)": "claude",
}
SECRET_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "ASSESSMENT_REVIEW_PROVIDER",
    "CLAUDE_MODEL",
    "ANTHROPIC_MODEL",
    "CLAUDE_REVIEW_MODE",
    "CLAUDE_API_TIMEOUT",
    "CLAUDE_CONNECT_TIMEOUT",
    "CLAUDE_RETRIES",
    "CLAUDE_REVIEW_BATCH_SIZE",
    "CLAUDE_MAX_TOKENS",
    "CLAUDE_FIELD_CHAR_LIMIT",
)
ALLOWED_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/pdf": ".pdf",
}
ANSWER_SHEET_ALLOWED_SUFFIXES = {".docx", ".pdf"}
ANSWER_SHEET_SOURCE_LABELS = {
    "ai_dynamic_review": "Dynamic AI review without answer sheet",
    "uploaded_answer_sheet_unmatched": "Uploaded answer sheet could not be matched to detected questions.",
    "mixed_uploaded_and_dynamic": "Partly matched uploaded answer sheet. Remaining questions use dynamic AI review.",
    "uploaded_answer_sheet": "Uploaded answer sheet",
}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            background:
                radial-gradient(circle at top left, rgba(196, 225, 255, 0.85), transparent 28%),
                radial-gradient(circle at top right, rgba(255, 230, 188, 0.7), transparent 24%),
                linear-gradient(180deg, #eef3f8 0%, #f8fafc 44%, #eef4f9 100%);
            color: #18324a;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #11293f 0%, #173854 100%);
        }
        [data-testid="stSidebar"] * {
            color: #f4f8fc;
        }
        [data-testid="stSidebar"] code {
            background: transparent !important;
            color: #f4f8fc !important;
            border: 0 !important;
            padding: 0 !important;
            font-size: inherit !important;
        }
        [data-testid="stHeader"] {
            background: transparent;
        }
        [data-testid="stToolbar"] {
            right: 0.75rem;
        }
        div[data-testid="stDecoration"] {
            display: none;
        }
        .block-container {
            padding-top: 0.15rem;
            padding-bottom: 1rem;
            max-width: 1040px;
        }
        .main .block-container > div:first-child {
            margin-top: 0;
            padding-top: 0;
        }
        [data-testid="stVerticalBlock"] > div:has(> .panel) {
            margin-bottom: 0.6rem;
        }
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid rgba(19, 53, 87, 0.08);
            border-radius: 18px;
            padding: 0.9rem 1rem;
            box-shadow: 0 18px 30px rgba(21, 38, 56, 0.08);
        }
        [data-testid="column"] {
            padding-top: 0;
        }
        div[data-testid="stFileUploader"] section {
            border-radius: 18px;
            border: 1px dashed rgba(18, 52, 88, 0.2);
            background: rgba(248, 251, 255, 0.95);
            padding: 0.35rem;
        }
        .hero {
            padding: 1.3rem 1.4rem 1.15rem 1.4rem;
            border-radius: 20px;
            background:
                radial-gradient(circle at top right, rgba(116, 190, 255, 0.18), transparent 30%),
                linear-gradient(135deg, rgba(11, 37, 64, 0.98), rgba(24, 76, 103, 0.96));
            color: #f8fbff;
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: 0 20px 38px rgba(23, 39, 58, 0.14);
            margin-bottom: 0.45rem;
        }
        .hero h1 {
            margin: 0 0 0.25rem 0;
            font-size: 2rem;
            line-height: 1.05;
        }
        .hero p {
            margin: 0;
            color: rgba(248, 251, 255, 0.88);
            font-size: 0.95rem;
            max-width: 44rem;
            line-height: 1.45;
        }
        .hero-strip {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            margin-top: 0.75rem;
        }
        .hero-chip {
            padding: 0.36rem 0.72rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.12);
            font-size: 0.78rem;
            font-weight: 600;
        }
        .panel {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(18, 52, 88, 0.08);
            border-radius: 18px;
            padding: 0.95rem 1rem;
            box-shadow: 0 12px 24px rgba(31, 48, 66, 0.07);
            margin: 0.05rem 0 0.45rem 0;
        }
        .mini-card {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(18, 52, 88, 0.08);
            border-radius: 16px;
            padding: 0.85rem 0.9rem;
            min-height: 92px;
            margin-bottom: 0.35rem;
            box-shadow: 0 10px 22px rgba(31, 48, 66, 0.05);
        }
        .mini-card h3 {
            margin: 0;
            color: #123458;
            font-size: 0.95rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        .mini-card p {
            margin: 0.45rem 0 0 0;
            color: #24384c;
            font-size: 0.95rem;
            line-height: 1.45;
        }
        .status-pill {
            display: inline-block;
            padding: 0.28rem 0.7rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-bottom: 0.95rem;
            color: #123458;
            background: #dceeff;
        }
        .question-card {
            padding: 1rem 1.05rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(18, 52, 88, 0.08);
            margin-top: 0.2rem;
        }
        div[data-testid="stExpander"] {
            margin-bottom: 0.45rem;
        }
        div[data-testid="stDownloadButton"] {
            margin-top: 0.45rem;
        }
        div[data-testid="stFileUploader"] {
            margin-top: 0.15rem;
            margin-bottom: 0.45rem;
        }
        div[data-testid="stButton"] {
            margin-top: 0.1rem;
        }
        div[data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.4rem;
        }
        .upload-note {
            margin-top: 0.5rem;
            padding: 0.75rem 0.82rem;
            border-radius: 16px;
            background: linear-gradient(135deg, rgba(228, 241, 255, 0.92), rgba(246, 249, 253, 0.96));
            border: 1px solid rgba(18, 52, 88, 0.08);
            color: #1c3954;
        }
        @media (max-width: 900px) {
            .block-container {
                padding-top: 0.25rem;
                padding-bottom: 0.9rem;
            }
            .hero {
                padding: 1.1rem 0.95rem;
            }
            .panel,
            .question-card,
            .mini-card {
                padding-left: 0.85rem;
                padding-right: 0.85rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _load_streamlit_secrets_to_env() -> None:
    try:
        secrets = st.secrets
    except Exception:
        return

    for key in SECRET_ENV_KEYS:
        if key in os.environ:
            continue
        try:
            value = secrets.get(key)
        except Exception:
            value = None
        if value is not None:
            os.environ[key] = str(value)


def _call_api(method: str, path: str, **kwargs: Any) -> requests.Response:
    return requests.request(
        method,
        f"{API_BASE_URL}{path}",
        timeout=(REQUEST_CONNECT_TIMEOUT, REQUEST_READ_TIMEOUT),
        **kwargs,
    )


def _backend_online() -> bool:
    try:
        response = _call_api("GET", "/health")
        return response.ok
    except requests.RequestException:
        return False


def _safe_filename(filename: str, fallback: str) -> str:
    return Path(filename or fallback).name


def _error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or "The request failed."

    if isinstance(payload, dict):
        return str(payload.get("detail") or payload)
    return str(payload)


def _is_allowed_upload(uploaded_file) -> bool:
    if uploaded_file is None:
        return False
    if uploaded_file.type in ALLOWED_TYPES:
        return True
    return Path(uploaded_file.name).suffix.lower() in {".docx", ".pdf"}


def _is_allowed_answer_sheet(uploaded_file) -> bool:
    if uploaded_file is None:
        return False
    return Path(uploaded_file.name).suffix.lower() in ANSWER_SHEET_ALLOWED_SUFFIXES


def _run_local_submission(uploaded_file) -> tuple[dict[str, Any] | None, bytes | None]:
    review_mode = st.session_state.get("review_mode", "Quick assessment")
    review_engine = st.session_state.get("review_engine", "Fast assessor (recommended)")
    review_provider = REVIEW_ENGINE_OPTIONS.get(review_engine, "local")
    review_id = uuid4().hex

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    original_name = _safe_filename(uploaded_file.name, "submission.docx")
    input_path = UPLOAD_DIR / f"{review_id}_{original_name}"
    output_path = OUTPUT_DIR / f"reviewed_{review_id}_{original_name}"
    input_path.write_bytes(uploaded_file.getvalue())

    answer_sheet_path = None
    answer_sheet_name = None
    answer_sheet = st.session_state.get("answer_sheet_upload")
    if review_mode == "Compare with answer sheet" and answer_sheet is not None:
        answer_sheet_name = _safe_filename(answer_sheet.name, "answer_sheet.docx")
        answer_sheet_path = UPLOAD_DIR / f"{review_id}_answersheet_{answer_sheet_name}"
        answer_sheet_path.write_bytes(answer_sheet.getvalue())

    try:
        result = run_pipeline(
            input_path,
            output_path,
            answer_sheet_path=answer_sheet_path,
            review_provider_override=review_provider,
        )
    except Exception as exc:
        st.error(f"Review failed: {exc}")
        return None, None

    payload = {
        "review_id": review_id,
        "original_filename": original_name,
        "reviewed_filename": f"reviewed_{original_name}",
        "download_url": "",
        "review_provider": result.get("review_provider", "local"),
        "review_provider_label": result.get("review_provider_label", DEFAULT_REVIEW_ENGINE_LABEL),
        "review_error": result.get("review_error"),
        "unit_id": result.get("unit_id"),
        "unit_name": result.get("unit_name"),
        "unit_file": result.get("unit_file"),
        "answer_sheet_filename": answer_sheet_name,
        "answer_sheet_source": result.get("answer_sheet_source", "ai_dynamic_review"),
        "answer_sheet_questions_matched": result.get("answer_sheet_questions_matched", 0),
        "answer_sheet_questions_missing": result.get("answer_sheet_questions_missing", 0),
        "answer_sheet_questions_matched_by_order": result.get("answer_sheet_questions_matched_by_order", 0),
        "summary": result["summary"],
        "assignment_summary": result["assignment_summary"],
        "results": result["results"],
    }

    reviewed_file = output_path.read_bytes() if output_path.exists() else None
    return payload, reviewed_file


def _judgement_badge(value: str) -> str:
    tone = {
        "Met": "#d8f1df",
        "Mostly relevant": "#e2ecff",
        "Partially met": "#fff0cf",
        "Insufficient evidence": "#ffe0cc",
        "Incorrect or off task": "#ffd7d9",
        "Not yet assessable": "#f1e3ff",
    }.get(value, "#e9eef5")
    return (
        f"<span style='display:inline-block;padding:0.25rem 0.7rem;border-radius:999px;"
        f"background:{tone};color:#17324d;font-weight:600;font-size:0.82rem;'>{value}</span>"
    )


def _render_overview() -> None:
    st.markdown(
        """
        <section class="hero">
            <div class="status-pill">Trial Version</div>
            <h1>AI Assessment Checker</h1>
            <p>Upload a student's Word or PDF submission, review it automatically, and return the same document with feedback inserted in place.</p>
            <div class="hero-strip">
                <span class="hero-chip">Same-file feedback</span>
                <span class="hero-chip">DOCX and PDF uploads</span>
                <span class="hero-chip">Claude-ready review flow</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            <div class="mini-card">
                <h3>Embedded Feedback</h3>
                <p>The reviewed output is the student's original file with feedback inserted where improvement is needed.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
            <div class="mini-card">
                <h3>Automated Review</h3>
                <p>The pipeline detects assignment questions dynamically, runs a fast assessor by default, and can use Claude when richer external review is selected.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_status() -> None:
    with st.sidebar:
        st.subheader("System Status")
        backend_ok = _backend_online()
        if backend_ok:
            st.success("Backend API online")
        else:
            st.info("Direct app mode active")

        st.caption(f"API URL: {API_BASE_URL}")
        st.write("Deployment mode: single Streamlit app supported")
        st.write("Student file: .docx or .pdf")
        st.write("Answer sheet: .docx or .pdf")
        st.write("Review engine: Fast assessor by default, Claude optional")
        st.write("Recommended structure: Q1, Q2, Q3 style questions with each answer directly underneath.")


def _submit_file(uploaded_file) -> tuple[dict[str, Any] | None, bytes | None]:
    if not _backend_online():
        return _run_local_submission(uploaded_file)

    review_mode = st.session_state.get("review_mode", "Quick assessment")
    review_engine = st.session_state.get("review_engine", "Fast assessor (recommended)")
    data = {"review_provider": REVIEW_ENGINE_OPTIONS.get(review_engine, "local")}
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/octet-stream",
        )
    }
    answer_sheet = st.session_state.get("answer_sheet_upload")
    if review_mode == "Compare with answer sheet" and answer_sheet is not None:
        files["answer_sheet"] = (
            answer_sheet.name,
            answer_sheet.getvalue(),
            answer_sheet.type or "application/octet-stream",
        )

    try:
        response = _call_api("POST", "/evaluate", files=files, data=data)
    except requests.ReadTimeout:
        st.error(
            "The review took too long to finish. Try a smaller DOCX/PDF file "
            "or increase `ASSESSMENT_API_READ_TIMEOUT`."
        )
        return None, None
    except requests.RequestException as exc:
        st.error(f"Could not contact the backend API: {exc}")
        return None, None
    if not response.ok:
        st.error(_error_message(response))
        return None, None

    payload = response.json()
    try:
        download_response = _call_api("GET", payload["download_url"])
    except requests.ReadTimeout:
        st.error("The review finished, but downloading the reviewed file took too long.")
        return payload, None
    except requests.RequestException as exc:
        st.error(f"The review finished, but the reviewed file could not be downloaded: {exc}")
        return payload, None
    if not download_response.ok:
        st.error("The review finished, but the reviewed file could not be downloaded.")
        return payload, None

    return payload, download_response.content


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return payload

    summary = payload.setdefault("summary", {})
    total_questions = summary.get("total_questions", 0)
    summary.setdefault("markers_found", 0)
    summary.setdefault("markers_missing", max(total_questions - summary["markers_found"], 0))

    for item in payload.get("results", []):
        item.setdefault("marker_found", False)
        item.setdefault("matched_marker", None)
        item.setdefault("matched_text", None)

    payload.setdefault("answer_sheet_source", "ai_dynamic_review")
    payload.setdefault("answer_sheet_questions_matched", 0)
    payload.setdefault("answer_sheet_questions_missing", total_questions)
    payload.setdefault("answer_sheet_questions_matched_by_order", 0)
    payload.setdefault("review_provider", "local")
    payload.setdefault("review_provider_label", DEFAULT_REVIEW_ENGINE_LABEL)
    payload.setdefault("review_error", None)
    payload.setdefault(
        "assignment_summary",
        {
            "overall_judgement": "Not yet assessable",
            "readiness": "No assignment summary was returned by the backend.",
            "summary_text": "No assignment summary was returned by the backend.",
            "completion_rate": 0,
            "pass_rate": 0,
            "total_answer_words": 0,
            "strengths": [],
            "priority_actions": [],
        },
    )

    return payload


def _render_submission() -> None:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.subheader("Review Submission")
    review_mode = st.radio(
        "Review mode",
        ["Quick assessment", "Compare with answer sheet"],
        horizontal=True,
        help="Use Quick assessment for the faster assessor-style review. Use Compare with answer sheet only when you want direct answer matching.",
        key="review_mode",
    )
    st.selectbox(
        "Assessment engine",
        list(REVIEW_ENGINE_OPTIONS),
        index=0,
        help=(
            "Fast assessor returns feedback quickly using the local assessment rules. "
            "Claude assessor can provide richer comments but may take much longer."
        ),
        key="review_engine",
    )
    uploaded = st.file_uploader(
        "Upload student assignment",
        type=["docx", "pdf"],
        help="Upload the student submission as DOCX or PDF for review and feedback generation.",
    )
    answer_sheet = None
    if review_mode == "Compare with answer sheet":
        answer_sheet = st.file_uploader(
            "Upload answer sheet",
            type=["docx", "pdf"],
            help="Upload the assessor answer sheet as DOCX or PDF so the app can match answers against it.",
            key="answer_sheet_upload",
        )
        st.markdown(
            """
            <div class="upload-note">
                <strong>Answer-sheet rule:</strong> upload the answer sheet in <code>.docx</code> or <code>.pdf</code> format.
                DOCX is still the most reliable option when you need cleaner text extraction and placement.
            </div>
            """,
            unsafe_allow_html=True,
        )

    can_submit = uploaded is not None
    if st.button("Run Assessment Review", type="primary", use_container_width=True, disabled=not can_submit):
        if not _is_allowed_upload(uploaded):
            st.error("Unsupported file type. Use a DOCX or PDF file.")
        elif review_mode == "Compare with answer sheet" and not answer_sheet:
            st.error("Upload the answer sheet in DOCX or PDF format to run comparison mode.")
        elif answer_sheet and not _is_allowed_answer_sheet(answer_sheet):
            st.error("Unsupported answer sheet type. Use a DOCX or PDF file.")
        else:
            with st.spinner("Reviewing submission and generating assessor feedback..."):
                payload, reviewed_file = _submit_file(uploaded)
            if payload:
                st.session_state["review_payload"] = payload
                st.session_state["review_file"] = reviewed_file

    if review_mode == "Quick assessment":
        st.caption("Quick assessment detects questions dynamically and reviews the uploaded assignment without any preloaded rubric JSON.")
    else:
        st.caption("Comparison mode uses the uploaded DOCX or PDF answer sheet as extra assessor context for dynamic AI review.")
    st.markdown("</div>", unsafe_allow_html=True)


def _render_summary(payload: dict[str, Any], reviewed_file: bytes | None) -> None:
    summary = payload["summary"]
    assignment_summary = payload.get("assignment_summary", {})
    results = payload["results"]
    markers_found = summary.get("markers_found", 0)
    markers_missing = summary.get("markers_missing", summary.get("total_questions", 0) - markers_found)
    improvement_items = (
        summary["partially_met"]
        + summary["insufficient_evidence"]
        + summary["incorrect_or_off_task"]
        + summary["not_yet_assessable"]
    )

    st.subheader("Review Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Questions", summary["total_questions"])
    m2.metric("Answered", summary["answered_questions"])
    m3.metric("Met", summary["met"])
    m4.metric("Needs Attention", improvement_items)
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown("### AI Assessor Summary")
    st.markdown(f"**Overall judgement:** `{assignment_summary.get('overall_judgement', 'Not yet assessable')}`")
    st.write(assignment_summary.get("summary_text", "No assignment summary was returned."))
    sm1, sm2, sm3 = st.columns(3)
    sm1.metric("Completion", f"{assignment_summary.get('completion_rate', 0)}%")
    sm2.metric("Met / Mostly Relevant", f"{assignment_summary.get('pass_rate', 0)}%")
    sm3.metric("Answer Words", assignment_summary.get("total_answer_words", 0))
    strengths = assignment_summary.get("strengths") or []
    actions = assignment_summary.get("priority_actions") or []
    if strengths:
        st.markdown("**Strengths detected**")
        for strength in strengths:
            st.write(f"- {strength}")
    if actions:
        st.markdown("**Priority actions**")
        for action in actions:
            st.write(f"- {action}")
    st.markdown("</div>", unsafe_allow_html=True)
    info1, info2 = st.columns([1.2, 1])
    with info1:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown(f"**Review scope:** {payload.get('unit_name') or 'Dynamic AI assessor review'}")
        st.markdown(f"**Review engine:** `{payload.get('review_provider_label', DEFAULT_REVIEW_ENGINE_LABEL)}`")
        if payload.get("review_error"):
            st.warning(f"Claude status: {payload['review_error']}")
        st.markdown(f"**Original file:** `{payload['original_filename']}`")
        if payload.get("answer_sheet_filename"):
            st.markdown(f"**Answer sheet:** `{payload['answer_sheet_filename']}`")
        else:
            st.markdown("**Answer sheet:** `Not provided`")
        st.markdown(
            f"**Answer sheet source:** {ANSWER_SHEET_SOURCE_LABELS.get(payload.get('answer_sheet_source'), payload.get('answer_sheet_source'))}"
        )
        st.markdown(
            f"**Answer sheet mapping:** `{payload.get('answer_sheet_questions_matched', 0)}` matched / `{payload.get('answer_sheet_questions_missing', 0)}` not matched"
        )
        if payload.get("answer_sheet_questions_matched_by_order", 0):
            st.markdown(
                f"**Order fallback used:** `{payload.get('answer_sheet_questions_matched_by_order', 0)}` question(s)"
            )
        st.markdown(f"**Reviewed output:** `{payload['reviewed_filename']}`")
        if reviewed_file:
            st.download_button(
                "Download Reviewed File",
                reviewed_file,
                file_name=payload["reviewed_filename"],
                mime="application/octet-stream",
                use_container_width=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
    with info2:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**Question Status**")
        st.write(f"Blank answers: `{summary['blank_questions']}`")
        st.write(f"Missing answers: `{summary['missing_questions']}`")
        st.write(f"Signs found in document: `{markers_found}`")
        st.write(f"Signs not found: `{markers_missing}`")
        st.write(f"Mostly relevant: `{summary['mostly_relevant']}`")
        st.write(f"Partially met: `{summary['partially_met']}`")
        st.write(f"Insufficient evidence: `{summary['insufficient_evidence']}`")
        st.write(f"Incorrect/off task: `{summary['incorrect_or_off_task']}`")
        st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Question-by-Question Review")
    table_rows = [
        {
            "Question": item["question_id"],
            "Sign Found": "Yes" if item.get("marker_found") else "No",
            "Judgement": item["judgement"],
            "Answer Status": item["answer_status"],
            "Words": item["answer_word_count"],
            "Target": item["minimum_words"],
            "Answer-Sheet Match": f"{int((item.get('answer_sheet_score') or 0) * 100)}%",
        }
        for item in results
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    for item in results:
        with st.expander(f"{item['question_id']} - {item['judgement']}"):
            st.markdown('<div class="question-card">', unsafe_allow_html=True)
            st.markdown(_judgement_badge(item["judgement"]), unsafe_allow_html=True)
            st.markdown(f"**Question:** {item['question']}")
            st.markdown(
                f"**Answer status:** `{item['answer_status']}` | **Words:** `{item['answer_word_count']}` / `{item['minimum_words']}`"
            )
            st.markdown(
                f"**Answer-sheet match:** `{int((item.get('answer_sheet_score') or 0) * 100)}%`"
            )
            st.markdown(
                f"**Detected sign found:** `{'Yes' if item.get('marker_found') else 'No'}`"
            )
            if item.get("matched_marker"):
                st.markdown(f"**Matched sign:** `{item['matched_marker']}`")
            if item.get("matched_text"):
                st.markdown(f"**Matched document text:** {item['matched_text']}")
            st.markdown(f"**Issue:** {item['issue']}")
            st.markdown(f"**Action required:** {item['action']}")
            if item["covered_points"]:
                st.markdown("**Covered points:** " + ", ".join(item["covered_points"]))
            if item["missing_points"]:
                st.markdown("**Missing points:** " + ", ".join(item["missing_points"]))
            if item.get("answer_sheet_covered_points"):
                st.markdown("**Matched answer-sheet ideas:** " + ", ".join(item["answer_sheet_covered_points"]))
            if item.get("answer_sheet_missing_points"):
                st.markdown("**Missing answer-sheet ideas:** " + ", ".join(item["answer_sheet_missing_points"]))
            st.markdown(f"**Feedback inserted into file:** {item['feedback']}")
            st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="AI Assessment Checker",
        page_icon="A",
        layout="wide",
    )
    _load_streamlit_secrets_to_env()
    _inject_styles()
    _render_status()
    _render_overview()
    _render_submission()

    payload = st.session_state.get("review_payload")
    payload = _normalize_payload(payload)
    if payload:
        st.session_state["review_payload"] = payload
    reviewed_file = st.session_state.get("review_file")
    if payload:
        _render_summary(payload, reviewed_file)


if __name__ == "__main__":
    main()
