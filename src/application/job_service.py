from typing import List, Optional
from sqlalchemy.orm import Session
from src.infrastructure.database.models import Job

class JobService:
    @staticmethod
    def create_job(db: Session, job_id: str, title: str, description: str, subject_tag: Optional[str] = None) -> Job:
        tag = subject_tag or f"ARG-{title.replace(' ', '-')}"
        existing = db.query(Job).filter(Job.job_id == job_id).first()
        if existing:
            existing.title = title
            existing.description = description
            existing.subject_tag = tag
            db.commit()
            db.refresh(existing)
            return existing

        new_job = Job(job_id=job_id, title=title, description=description, subject_tag=tag)
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        return new_job

    @staticmethod
    def get_all_jobs(db: Session) -> List[Job]:
        return db.query(Job).order_by(Job.created_at.desc()).all()

    @staticmethod
    def get_job_by_id(db: Session, job_id: str) -> Optional[Job]:
        return db.query(Job).filter(Job.job_id == job_id).first()
