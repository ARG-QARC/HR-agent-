import os
import imaplib
import email
from email.header import decode_header
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from src.infrastructure.pdf.extractor import extract_pdf_text
from src.infrastructure.database.models import Job, Candidate
from src.domain.scoring import score_resume_against_job

def extract_email_body(msg: email.message.Message) -> str:
    """Extracts plain text body from email message."""
    body_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disp:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_text += payload.decode(charset, errors="ignore")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body_text = payload.decode(charset, errors="ignore")
        except Exception:
            pass
    return body_text.strip()

def sync_resumes_from_gmail(db_session: Session) -> Dict[str, int]:
    """
    Connects to Gmail IMAP, scans unread & read emails, extracts attachments,
    scores candidate resumes, and saves records into the database.
    """
    email_user = os.environ.get("CONTACT_EMAIL", "").strip('"' + "'").strip()
    if not email_user:
        email_user = os.environ.get("LINKEDIN_EMAIL", "").strip('"' + "'").strip()

    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip('"' + "'").strip()
    if not app_password:
        app_password = os.environ.get("GMAIL_PASSWORD", "").strip('"' + "'").strip()

    if not email_user or not app_password:
        print("[GmailIMAP] Notice: Email credentials not configured.")
        return {"synced_count": 0, "scored_count": 0}

    active_jobs = db_session.query(Job).all()
    if not active_jobs:
        print("[GmailIMAP] Notice: No active jobs in database to match resumes.")
        return {"synced_count": 0, "scored_count": 0}

    active_tags = {}
    for j in active_jobs:
        active_tags[j.subject_tag.lower()] = j.job_id
        active_tags[j.job_id.lower()] = j.job_id

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, app_password.replace(" ", ""))
    except Exception as e:
        print(f"[GmailIMAP] Connection error: {e}")
        return {"synced_count": 0, "scored_count": 0}

    if os.environ.get("VERCEL"):
        save_dir = "/tmp/resumes"
    else:
        save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "resumes")

    os.makedirs(save_dir, exist_ok=True)

    folder = "Recruiting"
    status, _ = mail.select(folder)
    if status != 'OK':
        folder = "INBOX"
        mail.select(folder)

    status, data = mail.search(None, 'UNSEEN')
    if status != 'OK' or not data or not data[0]:
        status, data = mail.search(None, 'ALL')

    if status != 'OK' or not data or not data[0]:
        mail.logout()
        return {"synced_count": 0, "scored_count": 0}

    email_ids = data[0].split()
    synced_count = 0
    scored_count = 0

    for mail_id in email_ids:
        try:
            res, msg_data = mail.fetch(mail_id, "(RFC822)")
            if res != 'OK':
                continue

            for part_data in msg_data:
                if isinstance(part_data, tuple):
                    msg = email.message_from_bytes(part_data[1])
                    
                    subject_hdr = decode_header(msg["Subject"])[0]
                    subject = subject_hdr[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(subject_hdr[1] or "utf-8", errors="ignore")
                    subject = subject or "No Subject"

                    sender_hdr = decode_header(msg["From"])[0]
                    sender = sender_hdr[0]
                    if isinstance(sender, bytes):
                        sender = sender.decode(sender_hdr[1] or "utf-8", errors="ignore")
                    sender = sender or "Unknown Sender"

                    email_body = extract_email_body(msg)
                    subj_lower = subject.lower()
                    subj_norm = subj_lower.replace("-", " ").replace("_", " ")

                    matched_job_id = None
                    for tag, jid in active_tags.items():
                        tag_norm = tag.lower().replace("-", " ").replace("_", " ")
                        jid_norm = jid.lower().replace("-", " ").replace("_", " ")
                        if tag in subj_lower or jid in subj_lower or tag_norm in subj_norm or jid_norm in subj_norm:
                            matched_job_id = jid
                            break

                    if not matched_job_id:
                        for j in active_jobs:
                            t_norm = j.title.lower().replace("-", " ").replace("_", " ")
                            if j.title.lower() in subj_lower or t_norm in subj_norm:
                                matched_job_id = j.job_id
                                break

                    if not matched_job_id:
                        matched_job_id = active_jobs[0].job_id

                    job_obj = db_session.query(Job).filter(Job.job_id == matched_job_id).first()
                    if not job_obj:
                        continue

                    cand_name = sender.split("<")[0].strip() or "Candidate"
                    cand_email = sender.split("<")[-1].replace(">", "").strip() if "<" in sender else sender

                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart' or part.get("Content-Disposition") is None:
                            continue
                        
                        filename = part.get_filename()
                        if filename and filename.lower().endswith(".pdf"):
                            save_path = os.path.join(save_dir, f"{matched_job_id}_{cand_name}_{filename}")
                            with open(save_path, "wb") as f:
                                f.write(part.get_payload(decode=True))

                            extracted_text = extract_pdf_text(save_path)
                            eval_res = score_resume_against_job(job_obj.title, job_obj.description, extracted_text, email_body)

                            cand = db_session.query(Candidate).filter(
                                Candidate.job_id == matched_job_id,
                                Candidate.email == cand_email
                            ).first()

                            if not cand:
                                cand = Candidate(
                                    job_id=matched_job_id,
                                    name=cand_name,
                                    email=cand_email,
                                    resume_path=save_path,
                                    parsed_text=extracted_text,
                                    email_body=email_body,
                                    relevance_score=eval_res["relevance_score"],
                                    skills_score=eval_res["skills_score"],
                                    experience_score=eval_res["experience_score"],
                                    education_score=eval_res["education_score"],
                                    location_score=eval_res["location_score"],
                                    recommendation=eval_res["recommendation"],
                                    strengths="\n".join(eval_res["strengths"]),
                                    gaps="\n".join(eval_res["gaps"]),
                                    summary=eval_res["match_summary"],
                                    status="Scored"
                                )
                                db_session.add(cand)
                                synced_count += 1
                                scored_count += 1
                            else:
                                cand.resume_path = save_path
                                cand.parsed_text = extracted_text
                                cand.relevance_score = eval_res["relevance_score"]
                                cand.skills_score = eval_res["skills_score"]
                                cand.experience_score = eval_res["experience_score"]
                                cand.education_score = eval_res["education_score"]
                                cand.location_score = eval_res["location_score"]
                                cand.recommendation = eval_res["recommendation"]
                                cand.strengths = "\n".join(eval_res["strengths"])
                                cand.gaps = "\n".join(eval_res["gaps"])
                                cand.summary = eval_res["match_summary"]
                                cand.status = "Scored"
                                scored_count += 1
                            
                            db_session.commit()
        except Exception as err:
            print(f"[GmailIMAP] Notice on mail_id {mail_id}: {err}")

    try:
        mail.logout()
    except Exception:
        pass

    return {"synced_count": synced_count, "scored_count": scored_count}
