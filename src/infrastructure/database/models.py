import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)  # e.g., ARG-JD-001
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    subject_tag = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    candidates = relationship("Candidate", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_jobs_created_at", "created_at"),
    )

class Candidate(Base):
    __tablename__ = "candidates"

    candidate_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    resume_path = Column(String(500), nullable=True)
    parsed_text = Column(Text, nullable=True)
    email_body = Column(Text, nullable=True)
    
    # AI Evaluation Scores (0-100)
    relevance_score = Column(Integer, default=0, nullable=False)
    skills_score = Column(Integer, default=0, nullable=False)
    experience_score = Column(Integer, default=0, nullable=False)
    education_score = Column(Integer, default=0, nullable=False)
    location_score = Column(Integer, default=0, nullable=False)

    recommendation = Column(String(50), default="Pending", nullable=False)
    strengths = Column(Text, nullable=True)
    gaps = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    status = Column(String(50), default="Applied", nullable=False)
    applied_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    job = relationship("Job", back_populates="candidates")

    __table_args__ = (
        Index("idx_candidates_job_score", "job_id", "relevance_score"),
        CheckConstraint("relevance_score >= 0 AND relevance_score <= 100", name="chk_relevance_score_range"),
    )
