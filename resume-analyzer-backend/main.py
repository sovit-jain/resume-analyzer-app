from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from ai_analyzer import analyze_resume
from config import get_logger
from models import AnalyzeResumeAPIResponse
from resume_parser import extract_text_from_docx, extract_text_from_pdf

logger = get_logger(__name__)
app = FastAPI(title="Resume Analyzer API")
print("Resume Analyzer Backend is starting...")


@app.post("/analyze-resume", response_model=AnalyzeResumeAPIResponse)
async def analyze_resume_api(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    logger.info(
        "log-11 main.py | Received /analyze-resume request | filename=%s job_description_length=%d",
        resume.filename,
        len((job_description or "").strip()),
    )

    if not resume.filename:
        logger.warning("log-12 main.py | Request rejected because the uploaded file had no filename.")
        raise HTTPException(status_code=400, detail="Resume filename is missing.")

    filename = resume.filename.lower()

    try:
        if filename.endswith(".pdf"):
            logger.info("log-13 main.py | Parsing uploaded file as PDF | filename=%s", filename)
            resume_text = extract_text_from_pdf(resume.file)
        elif filename.endswith(".docx"):
            logger.info("log-14 main.py | Parsing uploaded file as DOCX | filename=%s", filename)
            resume_text = extract_text_from_docx(resume.file)
        else:
            logger.warning("log-15 main.py | Unsupported file format received | filename=%s", filename)
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Upload a PDF or DOCX file.",
            )

        logger.info("log-16 main.py | Resume parsed successfully | extracted_chars=%d", len(resume_text))
        analysis_result = analyze_resume(resume_text, job_description)
        logger.info(
            "log-17 main.py | Analysis finished | ats_score=%s strengths=%d missing_skills=%d",
            analysis_result.get("ats_score"),
            len(analysis_result.get("strengths", [])),
            len(analysis_result.get("missing_skills", [])),
        )
        return {"analysis": analysis_result}
    except HTTPException as exc:
        logger.warning("log-18 main.py | HTTP exception returned | status_code=%d detail=%s", exc.status_code, exc.detail)
        raise
    except Exception as exc:
        logger.exception("log-19 main.py | Unexpected failure while processing resume | filename=%s", filename)
        raise HTTPException(status_code=500, detail=f"Failed to analyze resume: {exc}") from exc