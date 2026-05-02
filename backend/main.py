from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
import uuid
import threading
import time

from ai_analyzer import analyze_resume
from config import get_logger
from models import AnalyzeResumeAPIResponse
from resume_parser import load_document, index_resumes, retrieve_relevant_resumes
from resume_parser import load_vector_store

logger = get_logger(__name__)
app = FastAPI(title="Resume Analyzer API")
print("Resume Analyzer Backend is starting...")

# Simple in-memory job store for async indexing jobs
index_job_store: dict = {}


@app.post("/analyze-resume", response_model=AnalyzeResumeAPIResponse)
async def analyze_resume_api(
    resumes: list[UploadFile] = File(...),
    job_description: str = Form(...),
):
    logger.info(
        "log-11 main.py | Received /analyze-resume request | files_count=%d job_description_length=%d",
        len(resumes),
        len((job_description or "").strip()),
    )
    if not resumes:
        logger.warning("log-12 main.py | No files uploaded in request.")
        raise HTTPException(status_code=400, detail="No resume files uploaded.")

    try:
        # Load all resumes
        loaded = []
        for up in resumes:
            if not up.filename:
                continue
            filename = up.filename.lower()
            logger.info("log-13 main.py | Loading document with LangChain | filename=%s", filename)
            text = load_document(up.file, filename)
            loaded.append({"resume_id": str(uuid.uuid4()), "filename": filename, "text": text})

        if not loaded:
            logger.warning("log-14 main.py | No readable resumes after loading.")
            raise HTTPException(status_code=400, detail="No readable resume files uploaded.")

        # If only one resume uploaded, keep legacy single-resume analysis path
        if len(loaded) == 1:
            resume_text = loaded[0]["text"]
            logger.info("log-16 main.py | Single resume loaded | extracted_chars=%d", len(resume_text))
            analysis_result = analyze_resume(resume_text, job_description)
            logger.info(
                "log-17 main.py | Analysis finished | ats_score=%s strengths=%d missing_skills=%d",
                analysis_result.get("ats_score"),
                len(analysis_result.get("strengths", [])),
                len(analysis_result.get("missing_skills", [])),
            )
            return {"analysis": analysis_result}

        # Multiple resumes: index them into an ephemeral in-memory Chroma collection and rank
        # Use a temporary collection name and no persist_directory to avoid polluting the on-disk DB
        temp_collection = f"temp_{uuid.uuid4()}"
        vector_store = index_resumes(loaded, collection_name=temp_collection, persist_directory=None)
        ranked = retrieve_relevant_resumes(vector_store, job_description, top_n=10)

        # For top candidates, optionally compute detailed analysis (top 3)
        top_to_analyze = min(3, len(ranked))
        ranked_results = []
        for idx, item in enumerate(ranked):
            # find full text for this resume_id
            full = next((r for r in loaded if r["resume_id"] == item["resume_id" or ""]), None)
            analysis = None
            if idx < top_to_analyze and full:
                try:
                    analysis = analyze_resume(full["text"], job_description)
                except Exception:
                    analysis = None
            ranked_results.append({
                "resume_id": item["resume_id"],
                "filename": item.get("filename"),
                "score": item.get("score"),
                "top_snippets": item.get("top_snippets", []),
                "analysis": analysis,
            })

        logger.info("log-17.5 main.py | Ranked results prepared | count=%d", len(ranked_results))
        return {"ranked_results": ranked_results}
    except HTTPException as exc:
        logger.warning("log-18 main.py | HTTP exception returned | status_code=%d detail=%s", exc.status_code, exc.detail)
        raise
    except Exception as exc:
        logger.exception("log-19 main.py | Unexpected failure while processing resumes")
        raise HTTPException(status_code=500, detail=f"Failed to analyze resumes: {exc}") from exc



@app.post("/index-resumes")
async def index_resumes_api(
    resumes: list[UploadFile] = File(...),
    collection_name: str = Form("resumes_global"),
    persist_directory: str = Form("./chroma_db"),
):
    """Index uploaded resumes and persist them to disk for later ranking/querying."""
    logger.info("log-30 main.py | Received /index-resumes request | files_count=%d collection=%s", len(resumes), collection_name)
    if not resumes:
        raise HTTPException(status_code=400, detail="No resume files uploaded.")

    try:
        loaded = []
        for up in resumes:
            if not up.filename:
                continue
            text = load_document(up.file, up.filename.lower())
            loaded.append({"resume_id": str(uuid.uuid4()), "filename": up.filename.lower(), "text": text})

        if not loaded:
            raise HTTPException(status_code=400, detail="No readable resume files uploaded.")

        vector_store = index_resumes(loaded, collection_name=collection_name, persist_directory=persist_directory)
        return {"indexed_count": len(loaded), "collection_name": collection_name, "persist_directory": persist_directory}
    except Exception as exc:
        logger.exception("log-31 main.py | Failed to index resumes")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _index_worker(job_id: str, loaded: list[dict], collection_name: str, persist_directory: str):
    """Background worker to index resumes and update job store."""
    try:
        index_job_store[job_id]["status"] = "running"
        vector_store = index_resumes(loaded, collection_name=collection_name, persist_directory=persist_directory)
        index_job_store[job_id]["status"] = "completed"
        index_job_store[job_id]["indexed_count"] = len(loaded)
        index_job_store[job_id]["collection_name"] = collection_name
        index_job_store[job_id]["persist_directory"] = persist_directory
    except Exception as exc:
        index_job_store[job_id]["status"] = "failed"
        index_job_store[job_id]["error"] = str(exc)


@app.post("/start-index-resumes")
async def start_index_resumes_api(
    background_tasks: BackgroundTasks,
    resumes: list[UploadFile] = File(...),
    collection_name: str = Form("resumes_global"),
    persist_directory: str = Form("./chroma_db"),
):
    """Start indexing resumes in background. Returns a job_id to poll status."""
    logger.info("log-40 main.py | Received /start-index-resumes request | files_count=%d collection=%s", len(resumes), collection_name)
    if not resumes:
        raise HTTPException(status_code=400, detail="No resume files uploaded.")

    try:
        loaded = []
        for up in resumes:
            if not up.filename:
                continue
            text = load_document(up.file, up.filename.lower())
            loaded.append({"resume_id": str(uuid.uuid4()), "filename": up.filename.lower(), "text": text})

        if not loaded:
            raise HTTPException(status_code=400, detail="No readable resume files uploaded.")

        job_id = str(uuid.uuid4())
        index_job_store[job_id] = {"status": "pending", "created_at": time.time()}

        # Run background worker in thread via BackgroundTasks
        background_tasks.add_task(_index_worker, job_id, loaded, collection_name, persist_directory)

        return {"job_id": job_id, "status": "pending"}
    except Exception as exc:
        logger.exception("log-41 main.py | Failed to start indexing job")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/index-status")
async def index_status(job_id: str):
    """Check status of an async indexing job."""
    job = index_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/rank-resumes", response_model=AnalyzeResumeAPIResponse)
async def rank_resumes_api(
    job_description: str = Form(...),
    collection_name: str = Form("resumes_global"),
    persist_directory: str = Form("./chroma_db"),
    top_n: int = Form(10),
    min_years: int = Form(0),
    location_contains: str = Form(""),
    role_contains: str = Form(""),
    semantic_weight: float = Form(0.7),
    years_weight: float = Form(0.2),
    role_weight: float = Form(0.05),
    location_weight: float = Form(0.05),
):
    """Rank resumes from a persisted collection for the provided job description."""
    logger.info("log-32 main.py | Received /rank-resumes request | collection=%s top_n=%d", collection_name, top_n)
    try:
        vector_store = load_vector_store(collection_name=collection_name, persist_directory=persist_directory)
        # Convert empty filters to None for the retriever
        min_y = None if min_years == 0 else min_years
        loc = location_contains.strip() or None
        role = role_contains.strip() or None
        ranked = retrieve_relevant_resumes(
            vector_store,
            job_description,
            top_n=top_n,
            min_years=min_y,
            location_contains=loc,
            role_contains=role,
            semantic_weight=float(semantic_weight),
            years_weight=float(years_weight),
            role_weight=float(role_weight),
            location_weight=float(location_weight),
        )
        return {"ranked_results": ranked}
    except Exception as exc:
        logger.exception("log-33 main.py | Failed to rank resumes")
        raise HTTPException(status_code=500, detail=str(exc)) from exc