import json
import re

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import OPENAI_API_KEY, get_logger
from models import AnalysisResponse
from resume_parser import split_text, create_vector_store, retrieve_relevant_chunks, inspect_vector_store

logger = get_logger(__name__)

# ============================================================================
# LCEL CHAIN DEFINITION
# ============================================================================


def get_analysis_chain():
    """Creates and returns the LCEL chain for resume analysis"""
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model="gpt-4o-mini",
        temperature=0
    )
    
    output_parser = JsonOutputParser()
    
    # LCEL Chain: prompt | llm | output_parser
    chain = RESUME_ANALYZER_PROMPT | llm | output_parser
    
    logger.info("log-50 ai_analyzer.py | LCEL chain created successfully")
    return chain

STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "you", "your", "are", "from",
    "have", "has", "will", "our", "job", "role", "team", "into", "about", "who",
    "how", "but", "not", "all", "any", "can", "per", "using", "use", "their",
    "developer", "developers", "engineer", "engineers", "experience", "experienced",
    "looking", "seeking", "need", "needs", "required", "preferred", "skills",
    "skill", "knowledge", "ability", "abilities", "years", "plus",
}

PHRASE_NORMALIZATIONS = {
    "front end": "frontend",
    "front-end": "frontend",
    "back end": "backend",
    "back-end": "backend",
    "full stack": "fullstack",
    "full-stack": "fullstack",
    "react js": "react",
    "react.js": "react",
    "node js": "nodejs",
    "node.js": "nodejs",
    "next js": "nextjs",
    "next.js": "nextjs",
}

FRONTEND_HINTS = {"react", "javascript", "typescript", "html", "css", "angular", "vue", "nextjs", "tailwind", "bootstrap", "sass", "ui", "ux"}
BACKEND_HINTS = {"python", "java", "nodejs", "fastapi", "django", "flask", "api", "apis", "sql", "postgresql", "mysql", "mongodb", "redis"}


# ============================================================================
# LANGCHAIN PROMPT TEMPLATES
# ============================================================================

# System prompt template for ATS analysis
SYSTEM_PROMPT_TEMPLATE = "You are a precise ATS resume reviewer."

# User prompt template for analyzing resume against job description
USER_PROMPT_TEMPLATE = """Analyze the resume against the job description and return ONLY valid JSON with this exact schema:
{{
  "ats_score": integer between 0 and 100,
  "strengths": ["short bullet", "..."],
  "missing_skills": ["skill", "..."],
  "suggestions": ["actionable suggestion", "..."]
}}

Resume:
{resume_text}

Job Description:
{job_description}
"""

# Create the ChatPromptTemplate
# This combines system and user messages into one reusable template
RESUME_ANALYZER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT_TEMPLATE),
    ("user", USER_PROMPT_TEMPLATE)
])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _normalize_text(text: str) -> str:
    normalized = text.lower()
    for old, new in PHRASE_NORMALIZATIONS.items():
        normalized = normalized.replace(old, new)
    return normalized


def _extract_keywords(text: str) -> set[str]:
    normalized = _normalize_text(text)
    words = re.findall(r"[A-Za-z][A-Za-z0-9\+\#\.\-/]*", normalized)
    keywords = {
        word.strip(".,;:!?()[]{}")
        for word in words
        if word.strip(".,;:!?()[]{}") not in STOP_WORDS and len(word.strip(".,;:!?()[]{}")) > 2
    }

    base_keywords = set(keywords)
    expanded_keywords = set(base_keywords)

    if base_keywords & FRONTEND_HINTS:
        expanded_keywords.add("frontend")
    if base_keywords & BACKEND_HINTS:
        expanded_keywords.add("backend")
    if (base_keywords & FRONTEND_HINTS) and (base_keywords & BACKEND_HINTS):
        expanded_keywords.add("fullstack")

    return expanded_keywords


def _fallback_analysis(resume_text: str, job_description: str) -> dict:
    resume_keywords = _extract_keywords(resume_text)
    jd_keywords = _extract_keywords(job_description)

    # If the job description clearly requests frontend/back-end skills but the resume
    # contains none of those hint keywords, treat as a non-match to avoid false high scores.
    try:
        if (jd_keywords & FRONTEND_HINTS) and not (resume_keywords & FRONTEND_HINTS):
            logger.info("log-23.5 ai_analyzer.py | JD requests frontend skills but resume lacks frontend hints; forcing score=0")
            matched = []
            missing = sorted(jd_keywords - resume_keywords)
            score = 0
            suggestions = [f"The job description emphasizes frontend/UI skills but the resume contains no frontend hints. Consider adding: {', '.join(sorted(jd_keywords & FRONTEND_HINTS))}."]
            suggestions.append("Tailor your resume to include front-end technologies, UI/UX examples, and related projects.")
            return AnalysisResponse(
                ats_score=0,
                strengths=[],
                missing_skills=missing[:8],
                suggestions=suggestions,
            ).model_dump()
        if (jd_keywords & BACKEND_HINTS) and not (resume_keywords & BACKEND_HINTS):
            logger.info("log-23.6 ai_analyzer.py | JD requests backend skills but resume lacks backend hints; forcing score=0")
            matched = []
            missing = sorted(jd_keywords - resume_keywords)
            score = 0
            suggestions = [f"The job description emphasizes backend skills but the resume contains no backend hints. Consider adding: {', '.join(sorted(jd_keywords & BACKEND_HINTS))}."]
            suggestions.append("Tailor your resume to include backend technologies, APIs, and system design examples.")
            return AnalysisResponse(
                ats_score=0,
                strengths=[],
                missing_skills=missing[:8],
                suggestions=suggestions,
            ).model_dump()
    except Exception:
        # If any error occurs in this stricter check, fall back to normal behavior below
        logger.exception("log-23.7 ai_analyzer.py | Exception during frontend/backend hint check in fallback analysis")

    matched = sorted(resume_keywords & jd_keywords)
    missing = sorted(jd_keywords - resume_keywords)
    score = round((len(matched) / len(jd_keywords)) * 100) if jd_keywords else 0
    logger.info(
        "log-23 ai_analyzer.py | Fallback analysis used | resume_keywords=%d jd_keywords=%d matched=%d missing=%d score=%d",
        len(resume_keywords),
        len(jd_keywords),
        len(matched),
        len(missing),
        score,
    )

    suggestions = []
    if missing:
        suggestions.append(f"Highlight or add evidence for: {', '.join(missing[:5])}.")

    if score >= 80:
        suggestions.append("Strong match overall. Fine-tune your summary and latest projects for this specific role.")
    elif score >= 50:
        suggestions.append("Good base alignment. Add a few more role-specific keywords and measurable results.")
    else:
        suggestions.append("Tailor the summary and experience bullets more closely to the job description.")

    suggestions.append("Use quantified achievements and clear role-specific keywords.")

    return AnalysisResponse(
        ats_score=max(0, min(score, 100)),
        strengths=matched[:8] or ["Resume text was extracted successfully."],
        missing_skills=missing[:8],
        suggestions=suggestions,
    ).model_dump()


def analyze_resume(resume_text: str, job_description: str) -> dict:
    resume_text = (resume_text or "").strip()
    job_description = (job_description or "").strip()
    logger.info(
        "log-21 ai_analyzer.py | Starting resume analysis | resume_chars=%d job_description_chars=%d",
        len(resume_text),
        len(job_description),
    )
    logger.info(
        "log-21.5 ai_analyzer.py | OpenAI client enabled=%s",
        OPENAI_API_KEY is not None,
    )

    if not resume_text:
        logger.warning("log-34 ai_analyzer.py | Resume analysis aborted because no readable resume text was available.")
        return AnalysisResponse(
            ats_score=0,
            strengths=[],
            missing_skills=[],
            suggestions=["Could not extract readable text from the uploaded resume."],
        ).model_dump()

    if not job_description:
        logger.warning("log-35 ai_analyzer.py | Resume analysis aborted because the job description was empty.")
        return AnalysisResponse(
            ats_score=0,
            strengths=[],
            missing_skills=[],
            suggestions=["Please provide a job description for comparison."],
        ).model_dump()

    if OPENAI_API_KEY is None:
        logger.info("log-22 ai_analyzer.py | No OpenAI API key configured. Using fallback keyword analysis.")
        return _fallback_analysis(resume_text, job_description)

    try:
        logger.info("log-24 ai_analyzer.py | Starting LCEL chain analysis.")
        
        # Split resume text into chunks
        resume_chunks = split_text(resume_text)
        
        # Create vector store (in-memory for now, can add persist_directory later)
        vector_store = create_vector_store(resume_chunks)
        
        # Optional: Inspect vector store contents for debugging
        store_info = inspect_vector_store(vector_store)
        logger.info("log-24.1 ai_analyzer.py | Vector store info: %s", store_info)
        
        # Retrieve relevant chunks based on job description
        relevant_chunks = retrieve_relevant_chunks(vector_store, job_description, k=5)
        
        # Use retrieved chunks in the prompt
        resume_text = "\n\n---\n\n".join(
            f"[Relevant Chunk {i + 1}]\n{chunk}"
            for i, chunk in enumerate(relevant_chunks)
        )
        
        # Truncate inputs if too long to avoid token limits (rough estimate: ~4 chars per token)
        max_chars = 100000  # ~25k tokens, well under gpt-4o-mini limit
        if len(resume_text) > max_chars:
            resume_text = resume_text[:max_chars] + "..."
            logger.warning("log-24.2 ai_analyzer.py | Resume text truncated to %d chars", max_chars)
        if len(job_description) > max_chars:
            job_description = job_description[:max_chars] + "..."
            logger.warning("log-24.3 ai_analyzer.py | Job description truncated to %d chars", max_chars)
        
        # LCEL chain handles everything automatically
        chain = get_analysis_chain()
        
        result = chain.invoke({
            "resume_text": resume_text,
            "job_description": job_description
        })
        
        # Normalize result to match AnalysisResponse schema
        normalized = {
            "ats_score": int(result.get("ats_score", result.get("ATS_score", 0))),
            "strengths": result.get("strengths", []),
            "missing_skills": result.get("missing_skills", []),
            "suggestions": result.get("suggestions", []),
        }
        
        final_result = AnalysisResponse(**normalized).model_dump()
        logger.info(
            "log-25 ai_analyzer.py | LCEL analysis completed | ats_score=%s strengths=%d missing_skills=%d",
            final_result.get("ats_score"),
            len(final_result.get("strengths", [])),
            len(final_result.get("missing_skills", [])),
        )
        return final_result
    except Exception as exc:
        logger.exception("log-26 ai_analyzer.py | LCEL analysis failed. Falling back to keyword-based analysis. Error: %s", str(exc))
        return _fallback_analysis(resume_text, job_description)