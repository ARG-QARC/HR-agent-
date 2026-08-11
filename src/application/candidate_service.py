import asyncio
from typing import List
from sqlalchemy.orm import Session
from src.infrastructure.database.models import Candidate, Job
from src.domain.scoring import score_resume_against_job
from src.infrastructure.email.gmail_imap import sync_resumes_from_gmail

class CandidateService:
    @staticmethod
    def get_candidates_for_job(db: Session, job_id: str) -> List[Candidate]:
        return db.query(Candidate).filter(Candidate.job_id == job_id).order_by(Candidate.relevance_score.desc()).all()

    @staticmethod
    async def sync_and_score_resumes_async(db: Session):
        """Runs blocking IMAP email fetch & AI evaluation in a background worker thread using asyncio.to_thread()."""
        return await asyncio.to_thread(sync_resumes_from_gmail, db)

    @staticmethod
    async def score_single_candidate_async(db: Session, candidate_id: int):
        """Scores a single candidate using asyncio.to_thread() to avoid blocking FastAPI workers."""
        def _score():
            cand = db.query(Candidate).filter(Candidate.candidate_id == candidate_id).first()
            if not cand or not cand.job:
                return None
            
            res = score_resume_against_job(
                job_title=cand.job.title,
                job_description=cand.job.description,
                resume_text=cand.parsed_text or "",
                email_body=cand.email_body or ""
            )

            cand.relevance_score = res["relevance_score"]
            cand.skills_score = res["skills_score"]
            cand.experience_score = res["experience_score"]
            cand.education_score = res["education_score"]
            cand.location_score = res["location_score"]
            cand.recommendation = res["recommendation"]
            cand.strengths = "\n".join(res["strengths"])
            cand.gaps = "\n".join(res["gaps"])
            cand.summary = res["match_summary"]
            cand.status = "Scored"

            db.commit()
            db.refresh(cand)
            return cand

        return await asyncio.to_thread(_score)
