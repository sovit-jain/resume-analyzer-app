from pydantic import BaseModel, Field


class AnalysisResponse(BaseModel):
    ats_score: int = Field(ge=0, le=100)
    strengths: list[str]
    missing_skills: list[str]
    suggestions: list[str]


class AnalyzeResumeAPIResponse(BaseModel):
    analysis: AnalysisResponse