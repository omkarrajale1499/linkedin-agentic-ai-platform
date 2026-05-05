from pydantic import BaseModel, Field
from typing import Optional

class ResumeParseRequest(BaseModel):
    resume_text: str
    member_id:   Optional[str] = None

class ParsedResume(BaseModel):
    skills:           list[str] = Field(default_factory=list)
    years_experience: float = 0.0
    education:        list[dict] = Field(default_factory=list)
    job_titles:       list[str] = Field(default_factory=list)
    summary:          Optional[str] = None
