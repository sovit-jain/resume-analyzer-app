from pydantic import BaseModel, Field


class AnalysisResponse(BaseModel):
    ats_score: int = Field(ge=0, le=100)
    strengths: list[str]
    missing_skills: list[str]
    suggestions: list[str]


class RankedSnippet(BaseModel):
    text: str
    metadata: dict


class RankedResume(BaseModel):
    resume_id: str
    filename: str
    score: float
    top_snippets: list[RankedSnippet]
    analysis: AnalysisResponse | None = None


class AnalyzeResumeAPIResponse(BaseModel):
    analysis: AnalysisResponse | None = None
    ranked_results: list[RankedResume] | None = None