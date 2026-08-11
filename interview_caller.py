"""
interview_caller.py - Phase 3: Interview Invitation & Scheduling System

This module is completely separate from Phase 1 (Job Posting) and Phase 2 (Resume Downloading & Scoring).
It handles formatting and sending official Call for Interview invitation emails to candidates
via Gmail SMTP and updating candidate status in the database.
"""

import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load environmental variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path, override=True)


def send_interview_invitation_email(
    candidate_name: str,
    candidate_email: str,
    job_title: str,
    interview_date: str,
    interview_day: str,
    interview_time: str,
    interview_type: str = "Google Meet / Video Call",
    interview_location: str = "Online Meeting / Head Office",
    notes: str = ""
) -> tuple[bool, str]:
    """
    Phase 3 Core Function:
    Sends an official Call for Interview invitation email to the specified candidate using Gmail SMTP.
    Returns (success_boolean, status_message).
    """
    email_user = os.environ.get("CONTACT_EMAIL", "").strip('"' + "'").strip()
    if not email_user:
        email_user = os.environ.get("LINKEDIN_EMAIL", "").strip('"' + "'").strip()

    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip('"' + "'").strip()
    if not app_password:
        app_password = os.environ.get("GMAIL_PASSWORD", "").strip('"' + "'").strip()
    if not app_password:
        app_password = os.environ.get("LINKEDIN_PASSWORD", "").strip('"' + "'").strip()

    if app_password:
        app_password = app_password.replace(" ", "")

    if not email_user or not app_password:
        return False, "Error: Gmail credentials (CONTACT_EMAIL / GMAIL_APP_PASSWORD) not found in .env"

    company_name = os.environ.get("COMPANY_NAME", "Al Rahim Group").strip('"' + "'").strip()
    subject = f"Interview Invitation: {job_title} at {company_name}"

    notes_block = f"\nAdditional Instructions: {notes}\n" if notes and notes.strip() else ""

    email_body = f"""Dear {candidate_name},

Thank you for applying for the position of {job_title} at {company_name}. We were very impressed with your application and qualifications!

We would like to officially invite you for an interview:

📅 Date: {interview_day}, {interview_date}
⏰ Time: {interview_time}
📍 Format: {interview_type}
🔗 Location / Meeting Link: {interview_location}
{notes_block}
Please reply directly to this email to confirm your attendance.

Best regards,
Hiring Team
{company_name}
{email_user}
"""

    try:
        msg = MIMEText(email_body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = email_user
        msg["To"] = candidate_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_user, app_password)
            server.sendmail(email_user, [candidate_email], msg.as_string())

        print(f"[Phase 3] Successfully sent interview invitation email to {candidate_name} ({candidate_email})")
        return True, f"Interview invitation successfully sent to {candidate_email}"

    except Exception as e:
        print(f"[Phase 3] Error sending interview email to {candidate_email}: {e}")
        return False, f"Failed to send email: {e}"


def main():
    print("============================================================")
    print("PHASE 3: INTERVIEW CALL MODULE READY")
    print("============================================================")


if __name__ == "__main__":
    main()
