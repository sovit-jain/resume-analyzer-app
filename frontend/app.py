import logging
import os

import requests
import streamlit as st

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
        use_index = st.checkbox("Use persisted index (rank existing collection)")
        resume_files = None
        if not use_index:
            resume_files = st.file_uploader("Upload Resume(s)", type=["pdf", "docx"], accept_multiple_files=True)

        job_description = st.text_area(
            "Paste Job Description",
            height=240,
            placeholder="Paste the job description here...",
        )

        # Server-side filter options (shown when using persisted index)
        col1, col2, col3 = st.columns(3)
        with col1:
            collection_name = st.text_input("Collection name", value="resumes_global")
        with col2:
            persist_directory = st.text_input("Persist directory", value="./chroma_db")
        with col3:
            min_years_filter = st.number_input("Min years (server filter)", min_value=0, max_value=50, value=0)

        col4, col5 = st.columns(2)
        with col4:
            location_filter = st.text_input("Location contains (server filter)")
        with col5:
            role_filter = st.text_input("Role/title contains (server filter)")

        # Scoring weight sliders
        w1, w2, w3, w4 = st.columns(4)
        with w1:
            semantic_w = st.slider("Semantic weight", 0.0, 1.0, 0.7, 0.05)
        with w2:
            years_w = st.slider("Years weight", 0.0, 1.0, 0.2, 0.05)
        with w3:
            role_w = st.slider("Role weight", 0.0, 1.0, 0.05, 0.01)
        with w4:
            location_w = st.slider("Location weight", 0.0, 1.0, 0.05, 0.01)

        analyze_label = "Rank from index" if use_index else "Analyze Resume(s)"
        analyze_clicked = st.form_submit_button(analyze_label, use_container_width=True)
        # Allow indexing uploaded resumes into a persisted collection from the UI
        index_clicked = None
        if not use_index:
            index_clicked = st.form_submit_button("Index & Persist resumes", key="index_button")

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
            "log-2 frontend.py | Analyze clicked | use_index=%s resumes_provided=%s job_description_length=%d",
            use_index,
            bool(resume_files),
            len(job_description.strip()),
        )
        # Debug: log detailed info about uploaded resume files for troubleshooting
        if resume_files:
            try:
                file_names = [getattr(f, "name", str(f)) for f in resume_files]
                file_sizes = []
                for f in resume_files:
                    try:
                        b = f.getvalue()
                        file_sizes.append(len(b))
                    except Exception:
                        file_sizes.append(None)
                logger.info("log-2.1 frontend.py | Uploaded files count=%d names=%s sizes=%s", len(resume_files), file_names, file_sizes)
            except Exception:
                logger.info("log-2.1 frontend.py | Uploaded files present but failed to enumerate details")
        else:
            logger.info("log-2.1 frontend.py | No uploaded files present (resume_files is empty or None)")

        if use_index:
            if not job_description.strip():
                st.session_state["request_status"] = "Validation failed"
                logger.warning("log-4 frontend.py | Analysis blocked because the job description was empty.")
                st.warning("Please paste a job description.")
            else:
                st.session_state["request_status"] = "Sending rank request to backend"
                logger.info("log-5 frontend.py | Sending rank request to %s", RANK_URL)
                with st.spinner("Ranking resumes from persisted index..."):
                    try:
                        response = requests.post(
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
                        response.raise_for_status()
                        payload = response.json()
                        ranked = payload.get("ranked_results") or payload.get("ranked")
                        st.session_state["result"] = {"ranked_results": ranked}
                        st.session_state["request_status"] = "Completed"
                        st.success("Ranking completed successfully.")
                    except requests.RequestException as exc:
                        st.session_state["result"] = None
                        st.session_state["request_status"] = "Backend request failed"
                        logger.exception("log-7 frontend.py | Could not reach the backend for ranking.")
                        st.error(f"Could not reach the backend: {exc}")
                    except ValueError:
                        st.session_state["result"] = None
                        st.session_state["request_status"] = "Invalid backend response"
                        logger.exception("log-8 frontend.py | Backend returned invalid JSON for ranking.")
                        st.error("The backend returned an invalid JSON response.")
        else:
            # Non-index analysis: validate and send uploaded resumes to the backend
            if not resume_files:
                st.session_state["request_status"] = "Validation failed"
                logger.warning("log-3 frontend.py | Analysis blocked because no resume was uploaded.")
                st.warning("Please upload one or more resume files.")
            elif not job_description.strip():
                st.session_state["request_status"] = "Validation failed"
                logger.warning("log-4 frontend.py | Analysis blocked because the job description was empty.")
                st.warning("Please paste a job description.")
            else:
                # If user clicked the index button, send files to INDEX_URL to persist the collection
                if index_clicked:
                    # Start async indexing job and poll status
                    st.session_state["request_status"] = "Starting async indexing job"
                    files_payload = []
                    total_bytes = 0
                    for f in resume_files:
                        b = f.getvalue()
                        total_bytes += len(b)
                        files_payload.append((
                            "resumes",
                            (f.name, b, f.type or "application/octet-stream"),
                        ))
                    logger.info("log-5 frontend.py | Starting async indexing | files_count=%d total_bytes=%d collection=%s dir=%s", len(files_payload), total_bytes, collection_name, persist_directory)
                    with st.spinner("Starting background indexing job..."):
                        try:
                            start_url = INDEX_URL.replace("/index-resumes", "/start-index-resumes")
                            response = requests.post(
                                start_url,
                                files=files_payload,
                                data={"collection_name": collection_name, "persist_directory": persist_directory},
                                timeout=120,
                            )
                            response.raise_for_status()
                            payload = response.json()
                            job_id = payload.get("job_id")
                            st.session_state["request_status"] = "Indexing started"
                            st.success(f"Indexing job started: {job_id}")

                            # Poll for status (simple blocking poll with timeout)
                            status_url = INDEX_URL.replace("/index-resumes", "/index-status")
                            with st.spinner("Waiting for indexing to complete..."):
                                for _ in range(120):
                                    import time

                                    time.sleep(2)
                                    try:
                                        r = requests.get(status_url, params={"job_id": job_id}, timeout=10)
                                        if r.status_code == 200:
                                            j = r.json()
                                            st.session_state["request_status"] = j.get("status")
                                            if j.get("status") in ("completed", "failed"):
                                                if j.get("status") == "completed":
                                                    st.success(f"Indexing completed: {j.get('indexed_count')} resumes")
                                                else:
                                                    st.error(f"Indexing failed: {j.get('error')}")
                                                break
                                        else:
                                            # non-200; continue polling
                                            continue
                                    except requests.RequestException:
                                        continue
                                else:
                                    st.warning("Indexing still in progress (timeout polling). Check /index-status later.")
                        except requests.RequestException as exc:
                            st.session_state["request_status"] = "Indexing failed"
                            logger.exception("log-7 frontend.py | Could not reach the backend for async indexing.")
                            st.error(f"Async indexing start failed: {exc}")
                        except ValueError:
                            st.session_state["request_status"] = "Invalid backend response"
                            logger.exception("log-8 frontend.py | Backend returned invalid JSON for async indexing.")
                            st.error("The backend returned an invalid JSON response for async indexing.")
                else:
                    st.session_state["request_status"] = "Sending request to backend"
                    # Prepare files payload: support single and multiple uploads
                    files_payload = []
                    total_bytes = 0
                    for f in resume_files:
                        b = f.getvalue()
                        total_bytes += len(b)
                        files_payload.append((
                            "resumes",
                            (f.name, b, f.type or "application/octet-stream"),
                        ))
                    logger.info(
                        "log-5 frontend.py | Sending analysis request | files_count=%d total_bytes=%d",
                        len(files_payload),
                        total_bytes,
                    )
                    with st.spinner("Analyzing resume..."):
                        logger.info("log-5.5 frontend.py | About to send POST request to %s", BACKEND_URL)
                        try:
                            response = requests.post(
                                BACKEND_URL,
                                files=files_payload,
                                data={"job_description": job_description},
                                timeout=120,
                            )
                            response.raise_for_status()
                            payload = response.json()
                            # Backend may return either single analysis or ranked results for multiple resumes
                            analysis = payload.get("analysis") or payload.get("result")
                            ranked = payload.get("ranked_results") or payload.get("ranked")
                            if ranked:
                                st.session_state["result"] = {"ranked_results": ranked}
                            else:
                                st.session_state["result"] = analysis
                            st.session_state["request_status"] = "Completed"
                            logger.info(
                                "log-6 frontend.py | Analysis completed successfully | status_code=%d result_keys=%s",
                                response.status_code,
                                list((st.session_state.get("result") or {}).keys()),
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
    else:
        if not resume_files:
            st.session_state["request_status"] = "Validation failed"
            logger.warning("log-3 frontend.py | Analysis blocked because no resume was uploaded.")
            st.warning("Please upload one or more resume files.")
        elif not job_description.strip():
            st.session_state["request_status"] = "Validation failed"
            logger.warning("log-4 frontend.py | Analysis blocked because the job description was empty.")
            st.warning("Please paste a job description.")
        else:
            # If user clicked the index button, send files to INDEX_URL to persist the collection
            if index_clicked:
                # Start async indexing job and poll status
                st.session_state["request_status"] = "Starting async indexing job"
                files_payload = []
                total_bytes = 0
                for f in resume_files:
                    b = f.getvalue()
                    total_bytes += len(b)
                    files_payload.append((
                        "resumes",
                        (f.name, b, f.type or "application/octet-stream"),
                    ))
                logger.info("log-5 frontend.py | Starting async indexing | files_count=%d total_bytes=%d collection=%s dir=%s", len(files_payload), total_bytes, collection_name, persist_directory)
                with st.spinner("Starting background indexing job..."):
                    try:
                        start_url = INDEX_URL.replace("/index-resumes", "/start-index-resumes")
                        response = requests.post(
                            start_url,
                            files=files_payload,
                            data={"collection_name": collection_name, "persist_directory": persist_directory},
                            timeout=120,
                        )
                        response.raise_for_status()
                        payload = response.json()
                        job_id = payload.get("job_id")
                        st.session_state["request_status"] = "Indexing started"
                        st.success(f"Indexing job started: {job_id}")

                        # Poll for status (simple blocking poll with timeout)
                        status_url = INDEX_URL.replace("/index-resumes", "/index-status")
                        with st.spinner("Waiting for indexing to complete..."):
                            for _ in range(120):
                                import time

                                time.sleep(2)
                                try:
                                    r = requests.get(status_url, params={"job_id": job_id}, timeout=10)
                                    if r.status_code == 200:
                                        j = r.json()
                                        st.session_state["request_status"] = j.get("status")
                                        if j.get("status") in ("completed", "failed"):
                                            if j.get("status") == "completed":
                                                st.success(f"Indexing completed: {j.get('indexed_count')} resumes")
                                            else:
                                                st.error(f"Indexing failed: {j.get('error')}")
                                            break
                                    else:
                                        # non-200; continue polling
                                        continue
                                except requests.RequestException:
                                    continue
                            else:
                                st.warning("Indexing still in progress (timeout polling). Check /index-status later.")
                    except requests.RequestException as exc:
                        st.session_state["request_status"] = "Indexing failed"
                        logger.exception("log-7 frontend.py | Could not reach the backend for async indexing.")
                        st.error(f"Async indexing start failed: {exc}")
                    except ValueError:
                        st.session_state["request_status"] = "Invalid backend response"
                        logger.exception("log-8 frontend.py | Backend returned invalid JSON for async indexing.")
                        st.error("The backend returned an invalid JSON response for async indexing.")
            else:
                st.session_state["request_status"] = "Sending request to backend"
                # Prepare files payload: support single and multiple uploads
                files_payload = []
                total_bytes = 0
                for f in resume_files:
                    b = f.getvalue()
                    total_bytes += len(b)
                    files_payload.append((
                        "resumes",
                        (f.name, b, f.type or "application/octet-stream"),
                    ))
                logger.info(
                    "log-5 frontend.py | Sending analysis request | files_count=%d total_bytes=%d",
                    len(files_payload),
                    total_bytes,
                )
                with st.spinner("Analyzing resume..."):
                    logger.info("log-5.5 frontend.py | About to send POST request to %s", BACKEND_URL)
                    try:
                        response = requests.post(
                            BACKEND_URL,
                            files=files_payload,
                            data={"job_description": job_description},
                            timeout=120,
                        )
                        response.raise_for_status()
                        payload = response.json()
                        # Backend may return either single analysis or ranked results for multiple resumes
                        analysis = payload.get("analysis") or payload.get("result")
                        ranked = payload.get("ranked_results") or payload.get("ranked")
                        if ranked:
                            st.session_state["result"] = {"ranked_results": ranked}
                        else:
                            st.session_state["result"] = analysis
                        st.session_state["request_status"] = "Completed"
                        logger.info(
                            "log-6 frontend.py | Analysis completed successfully | status_code=%d result_keys=%s",
                            response.status_code,
                            list((st.session_state.get("result") or {}).keys()),
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
    # If backend returned ranked results for multiple resumes
    if isinstance(result, dict) and result.get("ranked_results"):
        st.divider()
        st.markdown("## Ranked Candidates")
        ranked = result.get("ranked_results", [])

        # Filters
        with st.expander("Filters", expanded=True):
            min_years = st.number_input("Min years experience", min_value=0, max_value=50, value=0)
            location_filter = st.text_input("Location contains (optional)")
            role_filter = st.text_input("Role/title contains (optional)")

        def matches_filters(item):
            meta = item.get("resume_metadata") or {}
            years = meta.get("years_experience")
            if years is not None and years < min_years:
                return False
            if location_filter:
                loc = (meta.get("location") or "")
                if location_filter.lower() not in loc.lower():
                    return False
            if role_filter:
                title = (meta.get("current_title") or "")
                if role_filter.lower() not in title.lower() and role_filter.lower() not in (item.get("filename") or "").lower():
                    return False
            return True

        filtered = [r for r in ranked if matches_filters(r)]

        st.markdown(f"**Showing {len(filtered)} of {len(ranked)} candidates**")
        for r in filtered:
            st.markdown(f"### {r.get('filename')} — Score: {round(r.get('score',0), 3)}")
            meta = r.get("resume_metadata") or {}
            info = []
            if meta.get("current_title"):
                info.append(f"Title: {meta.get('current_title')}")
            if meta.get("years_experience") is not None:
                info.append(f"Years: {meta.get('years_experience')}")
            if meta.get("location"):
                info.append(f"Location: {meta.get('location')}")
            if meta.get("email"):
                info.append(f"Email: {meta.get('email')}")
            if info:
                st.write(" • ".join(info))
            snippets = r.get("top_snippets", [])
            if snippets:
                st.markdown("**Top snippets:**")
                for s in snippets:
                    if isinstance(s, dict):
                        st.write(s.get("text"))
                    else:
                        st.write(s)
            if r.get("analysis"):
                st.markdown("**Detailed analysis (top candidate):**")
                a = r.get("analysis")
                st.write(f"ATS Score: {a.get('ats_score')}")
                st.write("Strengths:")
                for s in a.get("strengths", []):
                    st.write(f"- {s}")
            st.divider()
        st.stop()

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
