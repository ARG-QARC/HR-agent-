import datetime
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class CandidateEntity:
    job_id: str
    name: str
    email: str
    candidate_id: Optional[int] = None
    resume_path: Optional[str] = None
    parsed_text: Optional[str] = None
    email_body: Optional[str] = None
    relevance_score: int = 0
    skills_score: int = 0
    experience_score: int = 0
    education_score: int = 0
    location_score: int = 0
    recommendation: str = "Pending"
    strengths: Optional[List[str]] = None
    gaps: Optional[List[str]] = None
    summary: Optional[str] = None
    status: str = "Applied"
    applied_at: Optional[datetime.datetime] = None

    def is_scored(self) -> bool:
        return self.status == "Scored" and self.relevance_score > 0
