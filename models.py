import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from database import Base

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True) # e.g. ARG-JD-001
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    subject_tag = Column(String, unique=True, index=True, nullable=False) # e.g. ARG-JD-001
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Candidate(Base):
    __tablename__ = "candidates"

    candidate_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    resume_path = Column(String, nullable=False) # Path to local PDF file
    parsed_text = Column(Text, nullable=True) # Text content extracted via pdfplumber / Gemini OCR
    email_body = Column(Text, nullable=True) # Text body of candidate application email
    relevance_score = Column(Integer, nullable=True) # Total Rating from 0 to 100
    skills_score = Column(Integer, nullable=True) # Rating from 0 to 35
    experience_score = Column(Integer, nullable=True) # Rating from 0 to 35
    education_score = Column(Integer, nullable=True) # Rating from 0 to 15
    location_score = Column(Integer, nullable=True) # Rating from 0 to 15
    recommendation = Column(String, nullable=True) # HIRE, INTERVIEW, REJECT
    strengths = Column(Text, nullable=True) # Strengths bullet points or text
    gaps = Column(Text, nullable=True) # Gaps bullet points or text
    summary = Column(Text, nullable=True) # Gemini match analysis remarks
    status = Column(String, default="Applied") # e.g. Applied, Scored, Shortlisted
    applied_at = Column(DateTime, default=datetime.datetime.utcnow)
