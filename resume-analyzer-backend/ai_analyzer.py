import json
import re

from openai import OpenAI

from config import OPENAI_API_KEY, get_logger
from models import AnalysisResponse

logger = get_logger(__name__)
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
logger.info("log-20 ai_analyzer.py | AI analyzer initialized | openai_enabled=%s", client is not None)

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
        client is not None,
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

    if client is None:
        logger.info("log-22 ai_analyzer.py | No OpenAI API key configured. Using fallback keyword analysis.")
        return _fallback_analysis(resume_text, job_description)

    prompt = f"""
You are an expert ATS resume reviewer.
Analyze the resume against the job description and return ONLY valid JSON with this exact schema:
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

    try:
        logger.info("log-24 ai_analyzer.py | Sending prompt to OpenAI for ATS analysis.")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a precise ATS resume reviewer."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        normalized = {
            "ats_score": parsed.get("ats_score", parsed.get("ATS_score", 0)),
            "strengths": parsed.get("strengths", []),
            "missing_skills": parsed.get("missing_skills", []),
            "suggestions": parsed.get("suggestions", []),
        }
        result = AnalysisResponse(**normalized).model_dump()
        logger.info(
            "log-25 ai_analyzer.py | OpenAI analysis completed | ats_score=%s strengths=%d missing_skills=%d",
            result.get("ats_score"),
            len(result.get("strengths", [])),
            len(result.get("missing_skills", [])),
        )
        return result
    except Exception:
        logger.exception("log-26 ai_analyzer.py | OpenAI analysis failed. Falling back to keyword-based analysis.")
        return _fallback_analysis(resume_text, job_description)