import logging
import os
import requests
import streamlit as st
import time

from components.header import render_sidebar, render_hero
from components.styles import inject
from components.upload_panel import render_input_panel
from components.ats_dashboard import render_single_analysis
from components.ranking_table import render_ranking_results


BACKEND_URL = os.getenv("BACKEND_URL", "https://backend-service-812074477410.asia-south1.run.app/analyze-resume")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
RANK_URL = os.getenv("RANK_URL", "https://backend-service-812074477410.asia-south1.run.app/rank-resumes")
INDEX_URL = os.getenv("INDEX_URL", "https://backend-service-812074477410.asia-south1.run.app/index-resumes")

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
else:
    logging.getLogger().setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

logger = logging.getLogger("resume_analyzer.frontend")
logger.info("Streamlit UI initialized")

st.set_page_config(page_title="Recruiter ATS Dashboard", page_icon="📄", layout="wide")
inject()

if "result" not in st.session_state:
    st.session_state["result"] = None
if "request_status" not in st.session_state:
    st.session_state["request_status"] = "Idle"

# Sidebar and hero
nav = render_sidebar()
render_hero()

# Main tabs for modes
tab_single, tab_bulk = st.tabs(["Single Resume Analysis", "Bulk Resume Ranking"])

with tab_single:
    st.markdown("### Candidate / Resume Input")
    inputs = render_input_panel()

    # preserve old variable names for downstream logic
    use_index = inputs.get("use_index")
    resume_files = inputs.get("resume_files")
    job_description = inputs.get("job_description") or ""
    collection_name = inputs.get("collection_name")
    persist_directory = inputs.get("persist_directory")
    min_years_filter = inputs.get("min_years_filter")
    location_filter = inputs.get("location_filter")
    role_filter = inputs.get("role_filter")
    semantic_w = inputs.get("semantic_w")
    years_w = inputs.get("years_w")
    role_w = inputs.get("role_w")
    location_w = inputs.get("location_w")
    analyze_clicked = inputs.get("analyze_clicked")
    index_clicked = inputs.get("index_clicked")

    right_col = st.container()
    if analyze_clicked:
        st.session_state["request_status"] = "Validating input"
        if use_index:
            if not job_description.strip():
                st.warning("Please paste a job description.")
            else:
                st.session_state["request_status"] = "Ranking from index"
                try:
                    r = requests.post(
                        RANK_URL,
                        data={
                            "job_description": job_description,
                            "collection_name": collection_name,
                            "persist_directory": persist_directory,
                            "top_n": 20,
                            "min_years": int(min_years_filter),
                            "location_contains": location_filter,
                            "role_contains": role_filter,
                            "semantic_weight": float(semantic_w),
                            "years_weight": float(years_w),
                            "role_weight": float(role_w),
                            "location_weight": float(location_w),
                        },
                        timeout=60,
                    )
                    r.raise_for_status()
                    payload = r.json()
                    ranked = payload.get("ranked_results") or payload.get("ranked")
                    st.session_state["result"] = {"ranked_results": ranked}
                    st.success("Ranking completed")
                except Exception as exc:
                    logger.exception("Ranking failed")
                    st.error(f"Ranking failed: {exc}")
        else:
            if not resume_files:
                st.warning("Please upload one or more resume files.")
            elif not job_description.strip():
                st.warning("Please paste a job description.")
            else:
                # send files to backend for analysis
                files_payload = []
                total_bytes = 0
                for f in resume_files:
                    b = f.getvalue()
                    total_bytes += len(b)
                    files_payload.append(("resumes", (f.name, b, f.type or "application/octet-stream")))
                try:
                    response = requests.post(BACKEND_URL, files=files_payload, data={"job_description": job_description}, timeout=120)
                    response.raise_for_status()
                    payload = response.json()
                    analysis = payload.get("analysis") or payload.get("result")
                    ranked = payload.get("ranked_results") or payload.get("ranked")
                    st.session_state["page"] = 0
                    if ranked:
                        st.session_state["result"] = {"ranked_results": ranked}
                    else:
                        st.session_state["result"] = analysis
                    st.success("Analysis completed")
                except Exception as exc:
                    logger.exception("Analysis failed")
                    st.error(f"Analysis failed: {exc}")

    # Indexing option (background start)
    if index_clicked and resume_files:
        files_payload = []
        for f in resume_files:
            b = f.getvalue()
            files_payload.append(("resumes", (f.name, b, f.type or "application/octet-stream")))
        try:
            start_url = INDEX_URL.replace("/index-resumes", "/start-index-resumes")
            r = requests.post(start_url, files=files_payload, data={"collection_name": collection_name, "persist_directory": persist_directory}, timeout=120)
            r.raise_for_status()
            job_id = r.json().get("job_id")
            st.success(f"Indexing started: {job_id}")
        except Exception as exc:
            logger.exception("Index start failed")
            st.error(f"Indexing start failed: {exc}")

with tab_bulk:
    st.markdown("### Bulk Ranking / Candidates")
    # If there is a ranked result in session, show it here
    result = st.session_state.get("result")
    ranked = None
    if isinstance(result, dict) and result.get("ranked_results"):
        ranked = result.get("ranked_results")
    elif isinstance(result, list):
        ranked = result

    # Developer helper: load sample data to test UI (modal, cards) without backend
    if st.button("Load sample candidates (dev)"):
        sample = [
            {
                "resume_id": "c1",
                "filename": "Alice Johnson",
                "score": 92.4,
                "resume_metadata": {"current_title": "Senior ML Engineer", "years_experience": 6, "location": "San Francisco, CA"},
                "top_skills": ["Python", "TensorFlow", "NLP", "AWS"],
                "analysis": {"ats_score": 92, "strengths": ["NLP", "Modeling"], "suggestions": ["Add more system design details"]},
                "top_snippets": [{"text": "Built production NLP pipelines using TensorFlow and AWS."}],
            },
            {
                "resume_id": "c2",
                "filename": "Bob Lee",
                "score": 75.1,
                "resume_metadata": {"current_title": "Data Scientist", "years_experience": 4, "location": "Seattle, WA"},
                "top_skills": ["Pandas", "PyTorch", "SQL"],
                "analysis": {"ats_score": 75, "strengths": ["Data analysis"], "suggestions": ["Highlight ML projects"]},
            },
            {
                "resume_id": "c3",
                "filename": "Carla Gomez",
                "score": 58.3,
                "resume_metadata": {"current_title": "Software Engineer", "years_experience": 2, "location": "Austin, TX"},
                "top_skills": ["Java", "Kubernetes"],
                "analysis": {"ats_score": 58, "strengths": [], "suggestions": ["Include more relevant keywords"]},
            },
        ]
        st.session_state["result"] = {"ranked_results": sample}
        ranked = sample

    render_ranking_results(ranked or [])

    st.sidebar.markdown(f"**Request status:** {st.session_state.get('request_status')}")
