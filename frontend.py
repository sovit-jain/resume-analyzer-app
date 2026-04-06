import logging
import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000/analyze-resume")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
else:
    logging.getLogger().setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

logger = logging.getLogger("resume_analyzer.frontend")
logger.info("log-1 frontend.py | Streamlit UI initialized | backend_url=%s log_level=%s", BACKEND_URL, LOG_LEVEL)

st.set_page_config(page_title="Resume Analyzer", page_icon="📄", layout="wide")

st.markdown(
    """
    <style>
        .hero {
            padding: 1.2rem 1.4rem;
            border-radius: 16px;
            background: linear-gradient(135deg, #0f172a, #1d4ed8);
            color: white;
            margin-bottom: 1rem;
        }
        .card {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 1rem;
            margin-bottom: 0.75rem;
        }
        .pill {
            display: inline-block;
            padding: 0.35rem 0.65rem;
            border-radius: 999px;
            background: #dbeafe;
            color: #1d4ed8;
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

if "result" not in st.session_state:
    st.session_state["result"] = None
if "request_status" not in st.session_state:
    st.session_state["request_status"] = "Idle"

st.markdown(
    """
    <div class="hero">
        <h1 style="margin-bottom:0.2rem;">📄 AI Resume Analyzer</h1>
        <p style="margin:0; font-size:1rem;">Upload a resume, compare it to a job description, and review ATS-focused feedback instantly.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("How to use")
    st.markdown(
        """
        1. Upload a `PDF` or `DOCX` resume  
        2. Paste the target job description  
        3. Click **Analyze Resume**
        """
    )
    st.caption(f"Backend endpoint: `{BACKEND_URL}`")
    st.caption(f"Request status: `{st.session_state['request_status']}`")
    st.info("Tip: Match the wording of the job description in your summary and project bullets.")
    st.warning("⚠️ If ATS scores are always 100 or 0, set OPENAI_API_KEY environment variable for AI-powered analysis.")

    if st.button("Clear Results"):
        st.session_state["result"] = None
        st.session_state["request_status"] = "Idle"
        st.rerun()

left_col, right_col = st.columns([1, 1.25], gap="large")

with left_col:
    st.markdown("### Resume Input")
    with st.form("resume_form"):
        resume_file = st.file_uploader("Upload Resume", type=["pdf", "docx"])
        job_description = st.text_area(
            "Paste Job Description",
            height=240,
            placeholder="Paste the job description here...",
        )
        analyze_clicked = st.form_submit_button("Analyze Resume", use_container_width=True)

with right_col:
    st.markdown("### What you will get")
    st.markdown(
        """
        <div class="card">
            <div class="pill">ATS Match Overview</div>
            <ul>
                <li>Match score out of 100</li>
                <li>Strengths already present in the resume</li>
                <li>Missing keywords or skills to address</li>
                <li>Actionable suggestions to improve fit</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

if analyze_clicked:
    st.session_state["request_status"] = "Validating input"
    logger.info(
        "log-2 frontend.py | Analyze clicked | resume_provided=%s job_description_length=%d",
        resume_file is not None,
        len(job_description.strip()),
    )

    if resume_file is None:
        st.session_state["request_status"] = "Validation failed"
        logger.warning("log-3 frontend.py | Analysis blocked because no resume was uploaded.")
        st.warning("Please upload a resume file.")
    elif not job_description.strip():
        st.session_state["request_status"] = "Validation failed"
        logger.warning("log-4 frontend.py | Analysis blocked because the job description was empty.")
        st.warning("Please paste a job description.")
    else:
        file_bytes = resume_file.getvalue()
        st.session_state["request_status"] = "Sending request to backend"
        logger.info(
            "log-5 frontend.py | Sending analysis request | file_name=%s file_size_bytes=%d mime_type=%s",
            resume_file.name,
            len(file_bytes),
            resume_file.type or "application/octet-stream",
        )
        with st.spinner("Analyzing resume..."):
            logger.info("log-5.5 frontend.py | About to send POST request to %s", BACKEND_URL)
            try:
                response = requests.post(
                    BACKEND_URL,
                    files={
                        "resume": (
                            resume_file.name,
                            file_bytes,
                            resume_file.type or "application/octet-stream",
                        )
                    },
                    data={"job_description": job_description},
                    timeout=60,
                )
                response.raise_for_status()
                payload = response.json()
                analysis = payload.get("analysis")
                st.session_state["result"] = analysis
                st.session_state["request_status"] = "Completed"
                logger.info(
                    "log-6 frontend.py | Analysis completed successfully | status_code=%d ats_score=%s strengths=%d missing_skills=%d",
                    response.status_code,
                    analysis.get("ats_score") if analysis else None,
                    len(analysis.get("strengths", [])) if analysis else 0,
                    len(analysis.get("missing_skills", [])) if analysis else 0,
                )
                st.success("Analysis completed successfully.")
            except requests.RequestException as exc:
                st.session_state["result"] = None
                st.session_state["request_status"] = "Backend request failed"
                logger.exception("log-7 frontend.py | Could not reach the backend.")
                st.error(f"Could not reach the backend: {exc}")
            except ValueError:
                st.session_state["result"] = None
                st.session_state["request_status"] = "Invalid backend response"
                logger.exception("log-8 frontend.py | Backend returned invalid JSON.")
                st.error("The backend returned an invalid JSON response.")

result = st.session_state.get("result")

if result:
    st.divider()
    st.markdown("## Analysis Result")

    score = int(result.get("ats_score", 0))
    verdict = (
        "Excellent match" if score >= 80 else
        "Good potential" if score >= 60 else
        "Needs tailoring"
    )
    logger.info("log-9 frontend.py | Rendering analysis result in UI | ats_score=%d verdict=%s", score, verdict)

    metric_col, summary_col = st.columns([0.8, 1.2], gap="large")
    with metric_col:
        st.metric("ATS Score", f"{score}/100")
        st.progress(score / 100)
    with summary_col:
        st.markdown(f"### {verdict}")
        st.write("Review the strengths, gaps, and suggestions below to improve alignment with the role.")

    strengths_col, missing_col = st.columns(2, gap="large")

    with strengths_col:
        st.markdown("### ✅ Strengths")
        strengths = result.get("strengths", [])
        if strengths:
            for skill in strengths:
                st.markdown(f"- {skill}")
        else:
            st.write("No strengths were identified.")

    with missing_col:
        st.markdown("### ⚠️ Missing Skills")
        missing_skills = result.get("missing_skills", [])
        if missing_skills:
            for skill in missing_skills:
                st.markdown(f"- {skill}")
        else:
            st.write("No major missing skills detected.")

    st.markdown("### 💡 Suggestions")
    suggestions = result.get("suggestions", [])
    if suggestions:
        for suggestion in suggestions:
            st.markdown(f"- {suggestion}")
    else:
        st.write("No suggestions available yet.")
else:
    logger.info("log-10 frontend.py | No analysis result available yet.")
    st.caption("Upload a resume and run an analysis to see the results here.")