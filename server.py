import os
import time
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import datetime

import database
import models
from download_resumes import sync_resumes_from_email # Phase 2: Resume Downloader
from scoring import score_resume_against_job          # Phase 2: AI Evaluator Engine
from interview_caller import send_interview_invitation_email # Phase 3: Interview Call System

from fastapi.staticfiles import StaticFiles

# Create FastAPI app
app = FastAPI(title="Recruiting & Post Assistant API")

# Enable CORS (Allows the PWA frontend or local client to access the API endpoints)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve PDF resume files statically (use /tmp on Vercel)
if os.environ.get("VERCEL"):
    resumes_dir = "/tmp/resumes"
else:
    resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")

if not os.path.exists(resumes_dir):
    os.makedirs(resumes_dir, exist_ok=True)
app.mount("/resumes", StaticFiles(directory=resumes_dir), name="resumes")

from fastapi.responses import FileResponse

# Serve root URL
@app.get("/")
def read_root():
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "online", "message": "HR Agent API is active"}

# Initialize database tables on startup
@app.on_event("startup")
def startup_event():
    database.init_db()

# Pydantic Schemas for requests/responses
class JobCreate(BaseModel):
    title: str
    description: str

class JobResponse(BaseModel):
    job_id: str
    title: str
    description: str
    subject_tag: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class CandidateResponse(BaseModel):
    candidate_id: int
    job_id: str
    name: str
    email: str
    resume_path: str
    relevance_score: Optional[int] = None
    skills_score: Optional[int] = None
    experience_score: Optional[int] = None
    education_score: Optional[int] = None
    location_score: Optional[int] = None
    recommendation: Optional[str] = None
    strengths: Optional[str] = None
    gaps: Optional[str] = None
    summary: Optional[str] = None
    status: str
    applied_at: datetime.datetime

    class Config:
        from_attributes = True

# --- API Endpoints ---

@app.post("/api/jobs", response_model=JobResponse)
def create_job(job_data: JobCreate, db: Session = Depends(database.get_db)):
    """
    Creates a new Job in the database and generates a unique subject tag for applications.
    """
    # Count current jobs to generate incremental ID
    try:
        job_count = db.query(models.Job).count()
    except Exception:
        job_count = 0
        
    next_num = job_count + 1
    job_id = f"ARG-JD-{next_num:03d}"
    
    # Check if ID already exists (safeguard)
    existing = db.query(models.Job).filter(models.Job.job_id == job_id).first()
    if existing:
        job_id = f"ARG-JD-{int(time.time())}"

    # Clean the job title to create a clean subject tag (e.g., "ARG-Data Scientist")
    cleaned_title = " ".join(job_data.title.split())
    subject_tag = f"ARG-{cleaned_title}"

    # Check if subject tag already exists (safeguard uniqueness)
    existing_tag = db.query(models.Job).filter(models.Job.subject_tag == subject_tag).first()
    if existing_tag:
        # Append unique ID code if tag already exists for another post
        subject_tag = f"ARG-{cleaned_title}-{next_num:03d}"

    # Generate instructions to apply
    apply_instructions = f"\n\n👉 TO APPLY: Send your resume to danish.alrahimgroup@gmail.com with the subject line exactly containing '{subject_tag}'."
    description_with_apply = job_data.description + apply_instructions

    db_job = models.Job(
        job_id=job_id,
        title=job_data.title,
        description=description_with_apply,
        subject_tag=subject_tag
    )
    
    try:
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        return db_job
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error creating job: {e}")

@app.get("/api/jobs", response_model=List[JobResponse])
def get_jobs(db: Session = Depends(database.get_db)):
    """
    Returns all jobs created in the system.
    """
    return db.query(models.Job).order_by(models.Job.created_at.desc()).all()

@app.post("/api/sync-resumes")
def sync_resumes(db: Session = Depends(database.get_db)):
    """
    Triggers email sync to fetch unread candidate emails, extracts PDFs,
    and AUTOMATICALLY runs Gemini multi-dimensional AI scoring for all fetched candidates in one go!
    """
    try:
        new_resumes = sync_resumes_from_email(db_session=db)
        
        # Auto-Score all newly fetched unscored candidates immediately
        unscored_cands = db.query(models.Candidate).filter(models.Candidate.status == "Applied").all()
        scored_count = 0
        for cand in unscored_cands:
            job = db.query(models.Job).filter(models.Job.job_id == cand.job_id).first()
            if job:
                try:
                    res = score_resume_against_job(
                        job_title=job.title,
                        job_description=job.description,
                        resume_text=cand.parsed_text or "",
                        email_body=cand.email_body or ""
                    )
                    cand.relevance_score = res.get("score", 0)
                    cand.skills_score = res.get("skills_score")
                    cand.experience_score = res.get("experience_score")
                    cand.education_score = res.get("education_score")
                    cand.location_score = res.get("location_score")
                    cand.recommendation = res.get("recommendation")
                    
                    strengths = res.get("strengths", [])
                    cand.strengths = "\n".join(f"• {s}" for s in strengths) if isinstance(strengths, list) else str(strengths or "")

                    gaps = res.get("gaps", [])
                    cand.gaps = "\n".join(f"• {g}" for g in gaps) if isinstance(gaps, list) else str(gaps or "")

                    cand.summary = res.get("match_summary") or res.get("summary")
                    cand.status = "Scored"
                    db.add(cand)
                    scored_count += 1
                except Exception as ex:
                    print(f"Error auto-scoring candidate {cand.name}: {ex}")
        
        if scored_count > 0:
            db.commit()
            
        return {"status": "success", "synced_count": new_resumes, "scored_count": scored_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

@app.post("/api/score-candidates/{job_id}")
def score_candidates(job_id: str, db: Session = Depends(database.get_db)):
    """
    Triggers Gemini multi-dimensional scoring for candidates linked to the given job_id
    who have status 'Applied' (no score yet).
    """
    job = db.query(models.Job).filter(models.Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    # Get candidates that have not been scored yet
    candidates = db.query(models.Candidate).filter(
        models.Candidate.job_id == job_id,
        models.Candidate.status == "Applied"
    ).all()

    if not candidates:
        return {"status": "success", "scored_count": 0, "message": "No unscored candidates for this job."}

    scored_count = 0
    for cand in candidates:
        try:
            # Score candidate using Gemini multi-dimensional evaluator
            res = score_resume_against_job(
                job_title=job.title,
                job_description=job.description,
                resume_text=cand.parsed_text or "",
                email_body=cand.email_body or ""
            )
            
            cand.relevance_score = res.get("score", 0)
            cand.skills_score = res.get("skills_score")
            cand.experience_score = res.get("experience_score")
            cand.education_score = res.get("education_score")
            cand.location_score = res.get("location_score")
            cand.recommendation = res.get("recommendation")
            
            strengths = res.get("strengths", [])
            cand.strengths = "\n".join(f"• {s}" for s in strengths) if isinstance(strengths, list) else str(strengths or "")

            gaps = res.get("gaps", [])
            cand.gaps = "\n".join(f"• {g}" for g in gaps) if isinstance(gaps, list) else str(gaps or "")

            cand.summary = res.get("match_summary") or res.get("summary")
            cand.status = "Scored"
            db.add(cand)
            scored_count += 1
        except Exception as e:
            print(f"Failed to score candidate {cand.name}: {e}")

    try:
        db.commit()
        return {"status": "success", "scored_count": scored_count}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save scores: {e}")


@app.get("/api/candidates/{job_id}", response_model=List[CandidateResponse])
def get_candidates(job_id: str, db: Session = Depends(database.get_db)):
    """
    Returns candidates applying for the specific job, sorted by relevance score descending.
    """
    return db.query(models.Candidate).filter(
        models.Candidate.job_id == job_id
    ).order_by(models.Candidate.relevance_score.desc()).all()

@app.delete("/api/candidates/{candidate_id}")
def delete_candidate(candidate_id: int, db: Session = Depends(database.get_db)):
    """
    Deletes the candidate from the database and removes their PDF and TXT files from the laptop.
    """
    cand = db.query(models.Candidate).filter(models.Candidate.candidate_id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Delete local PDF resume
    if cand.resume_path and os.path.exists(cand.resume_path):
        try:
            os.remove(cand.resume_path)
            # Delete corresponding TXT file
            base, _ = os.path.splitext(cand.resume_path)
            txt_path = base + ".txt"
            if os.path.exists(txt_path):
                os.remove(txt_path)
        except Exception as e:
            print(f"Error removing files: {e}")

    try:
        db.delete(cand)
        db.commit()
        return {"status": "success", "message": f"Successfully deleted candidate {candidate_id}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error deleting candidate: {e}")


class InterviewEmailRequest(BaseModel):
    candidate_name: str
    candidate_email: str
    job_title: str
    interview_date: str
    interview_day: str
    interview_time: str
    interview_type: str
    interview_location: str
    notes: Optional[str] = ""

@app.post("/api/send-interview-email")
def send_interview_email_endpoint(req: InterviewEmailRequest):
    """
    Phase 3 Endpoint: Delegates to interview_caller.py module to dispatch interview invitation email.
    """
    success, message = send_interview_invitation_email(
        candidate_name=req.candidate_name,
        candidate_email=req.candidate_email,
        job_title=req.job_title,
        interview_date=req.interview_date,
        interview_day=req.interview_day,
        interview_time=req.interview_time,
        interview_type=req.interview_type,
        interview_location=req.interview_location,
        notes=req.notes or ""
    )

from fastapi.responses import FileResponse

@app.get("/api/candidate-pdf/{candidate_identifier}")
def get_candidate_pdf_file(candidate_identifier: str, db: Session = Depends(database.get_db)):
    """
    Returns the exact PDF resume file for a candidate by ID, filename, or fallback.
    """
    resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
    
    # 1. Try finding candidate in DB by numeric ID
    if candidate_identifier.isdigit():
        cand = db.query(models.Candidate).filter(models.Candidate.candidate_id == int(candidate_identifier)).first()
        if cand and cand.resume_path and os.path.exists(cand.resume_path):
            return FileResponse(cand.resume_path, media_type="application/pdf", filename=os.path.basename(cand.resume_path))

    # 2. Try finding exact filename match in resumes directory
    clean_name = os.path.basename(candidate_identifier)
    target_path = os.path.join(resumes_dir, clean_name)
    if os.path.exists(target_path) and target_path.lower().endswith(".pdf"):
        return FileResponse(target_path, media_type="application/pdf", filename=clean_name)

    if not clean_name.lower().endswith(".pdf"):
        target_path_pdf = os.path.join(resumes_dir, clean_name + ".pdf")
        if os.path.exists(target_path_pdf):
            return FileResponse(target_path_pdf, media_type="application/pdf", filename=clean_name + ".pdf")

    # 3. Fallback: Return first available PDF in resumes directory
    if os.path.exists(resumes_dir):
        files = [f for f in os.listdir(resumes_dir) if f.lower().endswith(".pdf")]
        if files:
            return FileResponse(os.path.join(resumes_dir, files[0]), media_type="application/pdf", filename=files[0])

    raise HTTPException(status_code=404, detail="PDF resume file not found.")



