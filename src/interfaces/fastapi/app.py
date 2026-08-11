import os
import asyncio
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import datetime

from src.infrastructure.database import database, models
from src.application.job_service import JobService
from src.application.candidate_service import CandidateService
from src.application.interview_service import InterviewService

def create_app() -> FastAPI:
    app = FastAPI(title="HR Agent API", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if os.environ.get("VERCEL"):
        resumes_dir = "/tmp/resumes"
    else:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        resumes_dir = os.path.join(root_dir, "resumes")

    os.makedirs(resumes_dir, exist_ok=True)
    app.mount("/resumes", StaticFiles(directory=resumes_dir), name="resumes")

    @app.on_event("startup")
    def startup_event():
        database.init_db()

    class JobCreate(BaseModel):
        job_id: str
        title: str
        description: str
        subject_tag: Optional[str] = None

    class InterviewPayload(BaseModel):
        candidate_email: str
        candidate_name: Optional[str] = "Candidate"
        job_title: Optional[str] = "Position"
        company_name: Optional[str] = "Al Rahim Group"
        interview_date: Optional[str] = "TBD"
        interview_day: Optional[str] = "TBD"
        interview_time: Optional[str] = "TBD"
        interview_type: Optional[str] = "Online Video Call"
        interview_location: Optional[str] = "Google Meet / Zoom"
        notes: Optional[str] = ""

    @app.get("/api/health")
    def health_check():
        return {"status": "online", "system": "HR Agent Clean Architecture"}

    @app.get("/api/jobs")
    def get_jobs(db: Session = Depends(database.get_db)):
        jobs = JobService.get_all_jobs(db)
        return jobs

    @app.post("/api/jobs")
    def create_job(job: JobCreate, db: Session = Depends(database.get_db)):
        created = JobService.create_job(db, job.job_id, job.title, job.description, job.subject_tag)
        return created

    @app.get("/api/candidates/{job_id}")
    def get_candidates(job_id: str, db: Session = Depends(database.get_db)):
        cands = CandidateService.get_candidates_for_job(db, job_id)
        return cands

    @app.post("/api/sync-resumes")
    async def sync_resumes_endpoint(db: Session = Depends(database.get_db)):
        # Non-blocking async execution using asyncio.to_thread
        res = await CandidateService.sync_and_score_resumes_async(db)
        return JSONResponse(content={
            "status": "success",
            "synced_count": res.get("synced_count", 0),
            "scored_count": res.get("scored_count", 0)
        })

    @app.post("/api/send-interview-email")
    async def send_interview_email_endpoint(payload: InterviewPayload):
        # Non-blocking async execution using asyncio.to_thread
        success, message = await InterviewService.send_interview_invitation_async(payload.dict())
        if not success:
            raise HTTPException(status_code=500, detail=message)
        return {"status": "success", "message": message}

    @app.get("/api/candidate-pdf/{cand_id}")
    def get_candidate_pdf(cand_id: str, db: Session = Depends(database.get_db)):
        if cand_id.isdigit():
            cand = db.query(models.Candidate).filter(models.Candidate.candidate_id == int(cand_id)).first()
            if cand and cand.resume_path and os.path.exists(cand.resume_path):
                return FileResponse(cand.resume_path, media_type="application/pdf", filename=os.path.basename(cand.resume_path))

        clean_name = os.path.basename(cand_id)
        target = os.path.join(resumes_dir, clean_name)
        if os.path.exists(target):
            return FileResponse(target, media_type="application/pdf", filename=clean_name)

        raise HTTPException(status_code=404, detail="Resume PDF not found.")

    @app.get("/")
    def read_root():
        root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        idx_path = os.path.join(root_path, "index.html")
        if os.path.exists(idx_path):
            return FileResponse(idx_path)
        return {"status": "online", "message": "HR Agent API is active"}

    @app.get("/{filename:path}")
    def serve_static_files(filename: str):
        root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        file_path = os.path.join(root_path, filename)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        idx_path = os.path.join(root_path, "index.html")
        if os.path.exists(idx_path):
            return FileResponse(idx_path)
        raise HTTPException(status_code=404, detail="File not found")

    return app

app = create_app()
