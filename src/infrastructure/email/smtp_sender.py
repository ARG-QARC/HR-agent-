import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Tuple

def send_interview_invitation_email(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Sends interview invitation email via SMTP with error handling."""
    candidate_email = payload.get("candidate_email", "").strip()
    candidate_name = payload.get("candidate_name", "Candidate").strip()
    job_title = payload.get("job_title", "Position").strip()
    company_name = payload.get("company_name", "Al Rahim Group").strip()
    interview_date = payload.get("interview_date", "TBD").strip()
    interview_day = payload.get("interview_day", "TBD").strip()
    interview_time = payload.get("interview_time", "TBD").strip()
    interview_type = payload.get("interview_type", "Online Video Call").strip()
    interview_location = payload.get("interview_location", "Google Meet / Zoom link to follow").strip()
    notes = payload.get("notes", "").strip()

    if not candidate_email:
        return False, "Error: Candidate email address is missing."

    email_user = os.environ.get("CONTACT_EMAIL", "").strip('"' + "'").strip()
    if not email_user:
        email_user = os.environ.get("LINKEDIN_EMAIL", "").strip('"' + "'").strip()

    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip('"' + "'").strip()
    if not app_password:
        app_password = os.environ.get("GMAIL_PASSWORD", "").strip('"' + "'").strip()

    if not email_user or not app_password:
        return False, "Error: Gmail credentials (CONTACT_EMAIL / GMAIL_APP_PASSWORD) not found."

    app_password = app_password.replace(" ", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎉 Interview Invitation: {job_title} at {company_name}"
    msg["From"] = f"{company_name} Talent Acquisition <{email_user}>"
    msg["To"] = candidate_email

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1e293b; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
          <div style="background-color: #0f172a; color: #ffffff; padding: 24px; text-align: center;">
            <h2 style="margin: 0; color: #38bdf8;">{company_name}</h2>
            <p style="margin: 4px 0 0 0; color: #94a3b8; font-size: 14px;">Talent Acquisition & Global Recruitment</p>
          </div>
          <div style="padding: 32px;">
            <p style="font-size: 16px;">Dear <strong>{candidate_name}</strong>,</p>
            <p>Congratulations! After reviewing your application, we are pleased to invite you for an interview for the position of <strong>{job_title}</strong> at {company_name}.</p>
            
            <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 16px; margin: 24px 0; border-radius: 4px;">
              <h3 style="margin-top: 0; color: #0f172a;">📅 Interview Details:</h3>
              <ul style="list-style: none; padding-left: 0; margin-bottom: 0;">
                <li style="margin-bottom: 8px;"><strong>Date & Day:</strong> {interview_day}, {interview_date}</li>
                <li style="margin-bottom: 8px;"><strong>Time:</strong> {interview_time}</li>
                <li style="margin-bottom: 8px;"><strong>Format:</strong> {interview_type}</li>
                <li style="margin-bottom: 0;"><strong>Location/Link:</strong> {interview_location}</li>
              </ul>
            </div>
            
            {f'<p><strong>Additional Notes:</strong><br>{notes}</p>' if notes else ''}
            
            <p style="margin-top: 24px;">Please reply to this email to confirm your availability.</p>
            <p>Best regards,<br><strong>Talent Acquisition Team</strong><br>{company_name}</p>
          </div>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_user, app_password)
            server.sendmail(email_user, [candidate_email], msg.as_string())
        return True, f"Successfully sent interview invitation email to {candidate_email}!"
    except Exception as e:
        return False, f"Failed to send email: {e}"
