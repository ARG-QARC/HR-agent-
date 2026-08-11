import os
import sys
import time
import imaplib
import email
import pdfplumber
from email.header import decode_header
from dotenv import load_dotenv
from google import genai

# Load environmental variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path, override=True)

# Force stdout/stderr to use UTF-8 encoding (prevents Windows Unicode print crashes)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip('"' + "'").strip()

def extract_scanned_pdf_with_gemini(pdf_path: str) -> str:
    """
    Uses Gemini Vision API to OCR and extract text directly from scanned or image-based PDF files.
    """
    if not GEMINI_API_KEY:
        print("[Gemini OCR] Skipped: GEMINI_API_KEY not configured.")
        return ""
    try:
        print(f"[Gemini OCR] Uploading & OCR reading scanned PDF: {os.path.basename(pdf_path)}...")
        client = genai.Client(api_key=GEMINI_API_KEY)
        uploaded_file = client.files.upload(file=pdf_path)

        # Wait if file is in processing state
        attempts = 0
        while uploaded_file.state == "PROCESSING" and attempts < 10:
            time.sleep(1)
            uploaded_file = client.files.get(name=uploaded_file.name)
            attempts += 1

        models_to_try = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"]
        extracted_text = ""

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        uploaded_file,
                        "This PDF contains a scanned resume image or low-text document. Perform accurate OCR to extract ALL text content (contact details, work experience, skills, education, certifications). Return ONLY the extracted raw text."
                    ]
                )
                if response and response.text:
                    extracted_text = response.text.strip()
                    print(f"[Gemini OCR] Successfully extracted {len(extracted_text.split())} words using {model_name}.")
                    break
            except Exception as err:
                print(f"[Gemini OCR] Attempt with model {model_name} failed: {err}")
                time.sleep(1)

        # Cleanup uploaded file from GenAI cloud
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass

        return extracted_text

    except Exception as e:
        print(f"[Gemini OCR] Exception processing {os.path.basename(pdf_path)}: {e}")
        return ""


def extract_pdf_to_txt(pdf_path: str) -> str:
    """
    Extracts text contents from a PDF file using pdfplumber.
    If extracted text is empty or under 50 words (scanned/image PDF),
    it uses Gemini Vision API to OCR and read the PDF directly.
    Saves the result to a matching .txt file and returns full text.
    """
    base_path, _ = os.path.splitext(pdf_path)
    txt_path = base_path + ".txt"
    full_text = ""

    try:
        text_content = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
                else:
                    text_content.append(f"[Page {page_idx+1}: Image or Empty]")

        full_text = "\n\n--- PAGE BREAK ---\n\n".join(text_content).strip()
    except Exception as e:
        print(f"pdfplumber extraction error for {os.path.basename(pdf_path)}: {e}")
        full_text = ""

    word_count = len(full_text.split())

    # Fallback to Gemini Vision API if text is empty or under 50 words
    if word_count < 50:
        print(f"-> Notice: PDF text word count is {word_count} (< 50 words). Triggering Gemini Vision OCR fallback...")
        gemini_text = extract_scanned_pdf_with_gemini(pdf_path)
        if gemini_text and len(gemini_text.split()) >= 10:
            full_text = gemini_text
            word_count = len(full_text.split())
            print(f"-> Successfully updated resume text via Gemini OCR ({word_count} words).")

    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"-> Parsed & saved resume text ({word_count} words): {os.path.basename(txt_path)}")
    except Exception as save_err:
        print(f"Error saving txt file {txt_path}: {save_err}")

    return full_text


def match_email_to_job_with_gemini(subject: str, email_body: str, resume_snippet: str, active_jobs: list) -> str:
    """
    Uses Gemini AI to classify which active job posting the candidate is applying for
    when no explicit subject tag is present in the email subject.
    active_jobs is a list of tuples: (job_id, title, description, subject_tag)
    Returns matched job_id string or None.
    """
    if not GEMINI_API_KEY or not active_jobs:
        return None

    jobs_summary = []
    for j_id, j_title, j_desc, j_tag in active_jobs:
        desc_snippet = j_desc.replace("\n", " ")[:350]
        jobs_summary.append(f"- Job ID: {j_id} | Title: {j_title} | Tag: {j_tag} | Requirements: {desc_snippet}")

    prompt = f"""You are an automated recruitment AI matching incoming candidate job applications to active job postings.

ACTIVE OPEN POSITIONS:
{chr(10).join(jobs_summary)}

INCOMING CANDIDATE APPLICATION:
Email Subject: {subject}
Email Body: {email_body[:1000] if email_body else '[No email body text]'}
Resume Text Snippet: {resume_snippet[:1000] if resume_snippet else '[No resume snippet]'}

Task: Analyze the email subject, email body, and resume snippet to determine which Active Job ID the candidate is applying for.
Return ONLY the exact Job ID (e.g. ARG-JD-001). If none of the active open positions match or if the email is unrelated, return ONLY 'NONE'."""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        for model_name in ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.6-flash"]:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                out_text = response.text.strip()
                
                for j_id, _, _, _ in active_jobs:
                    if j_id.lower() in out_text.lower():
                        print(f"[Gemini Job Matching] Classified email '{subject}' -> Job ID: {j_id}")
                        return j_id

                if "NONE" in out_text.upper():
                    return None
            except Exception as model_err:
                print(f"[Gemini Job Matching] Model {model_name} error: {model_err}")
                time.sleep(1)
    except Exception as e:
        print(f"[Gemini Job Matching] Failed: {e}")

    return None


def extract_email_body_text(msg) -> str:
    """Extracts plain text body from an email message object."""
    email_body = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        email_body = payload.decode(charset, errors="ignore")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                email_body = payload.decode(charset, errors="ignore")
    except Exception as e:
        print(f"Error extracting email body text: {e}")

    return email_body.strip()


def sync_resumes_from_email(db_session=None):
    """
    Connects to Gmail, scans unseen emails, parses PDF resumes (using pdfplumber with Gemini OCR fallback),
    matches emails to jobs via subject tags or Gemini AI classification,
    saves PDF & text files locally, and records candidates in the database.
    """
    print("============================================================")
    print("RESUME DOWNLOADER BOT STARTING...")
    print("============================================================")

    # Fetch email credentials
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
        print("Error: Email username or password not found in .env file.")
        return 0

    # Load active jobs list from DB if session exists
    active_jobs = []
    active_tags = {}
    if db_session:
        from models import Job
        try:
            jobs = db_session.query(Job).all()
            for j in jobs:
                active_jobs.append((j.job_id, j.title, j.description, j.subject_tag))
                active_tags[j.subject_tag.lower()] = j.job_id
                active_tags[j.job_id.lower()] = j.job_id
            print(f"Loaded {len(active_jobs)} active job(s) from database.")
        except Exception as e:
            print(f"Error loading jobs from DB: {e}")

    print(f"Connecting to Gmail account: {email_user}...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, app_password)
    except Exception as e:
        print(f"Error logging into Gmail: {e}")
        print("\nNote: Google blocks standard password logins by default for security.")
        print("Please generate an 'App Password' from Google Security settings and paste it into GMAIL_APP_PASSWORD in .env.")
        return 0

    save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Select folder ("Recruiting", fallback to "INBOX")
    folder_selected = "Recruiting"
    status, _ = mail.select(folder_selected)
    
    if status != 'OK':
        print("Label 'Recruiting' not found in Gmail. Scanning Inbox instead...")
        folder_selected = "INBOX"
        mail.select(folder_selected)

    status, data = mail.search(None, 'UNSEEN')
    if status != 'OK' or not data or not data[0]:
        print("No unread emails found in UNSEEN. Checking all recent emails...")
        status, data = mail.search(None, 'ALL')

    if status != 'OK' or not data or not data[0]:
        print("No emails found to scan.")
        mail.logout()
        return 0

    email_ids = data[0].split()
    print(f"Found {len(email_ids)} unread email(s) to scan. Processing...")

    download_count = 0

    for mail_id in email_ids:
        try:
            res, msg_data = mail.fetch(mail_id, "(RFC822)")
            if res != 'OK':
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject_header = decode_header(msg["Subject"])[0]
                    subject = subject_header[0]
                    encoding = subject_header[1]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8", errors="ignore")
                    subject = subject or "No Subject"

                    sender_header = decode_header(msg["From"])[0]
                    sender = sender_header[0]
                    encoding = sender_header[1]
                    if isinstance(sender, bytes):
                        sender = sender.decode(encoding or "utf-8", errors="ignore")
                    sender = sender or "Unknown Sender"

                    email_body = extract_email_body_text(msg)
                    subj_lower = subject.lower()

                    # ── Job Matching Logic ──
                    matched_job_id = None

                    # 1. Match subject tag / job ID / job title in subject line
                    if active_tags:
                        for tag, jid in active_tags.items():
                            if tag in subj_lower or jid.lower() in subj_lower or jid.split("-")[-1] in subj_lower:
                                matched_job_id = jid
                                break
                    
                    if not matched_job_id and active_jobs:
                        for jid, title, desc, tag in active_jobs:
                            if title and title.lower() in subj_lower:
                                matched_job_id = jid
                                break

                    # 2. Filter unrelated inbox emails if folder is INBOX
                    if not matched_job_id and folder_selected == "INBOX":
                        keywords = ["al rahim group", "job application", "data scientist", "ai engineer", "engineer", "manager", "developer", "hiring", "recruiting", "resume", "cv", "application"]
                        if not any(kw in subj_lower for kw in keywords) and not any(kw in email_body.lower() for kw in keywords):
                            # Skip personal/unrelated emails and do NOT mark as read
                            continue

                    print(f"\nProcessing email: '{subject}' from {sender}")

                    # Walk through attachments and process PDFs
                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue

                        filename = part.get_filename()
                        if filename:
                            decoded_filename_header = decode_header(filename)[0]
                            decoded_filename = decoded_filename_header[0]
                            encoding = decoded_filename_header[1]
                            if isinstance(decoded_filename, bytes):
                                decoded_filename = decoded_filename.decode(encoding or "utf-8", errors="ignore")

                            if decoded_filename and decoded_filename.lower().endswith(".pdf"):
                                safe_filename = os.path.basename(decoded_filename)
                                filepath = os.path.join(save_dir, safe_filename)

                                if os.path.exists(filepath):
                                    base, ext = os.path.splitext(safe_filename)
                                    filepath = os.path.join(save_dir, f"{base}_{int(time.time())}{ext}")

                                print(f"-> Extracting PDF attachment: {decoded_filename}")
                                with open(filepath, "wb") as f:
                                    f.write(part.get_payload(decode=True))
                                
                                # Extract text with pdfplumber + Gemini OCR fallback for scanned PDFs
                                resume_text = extract_pdf_to_txt(filepath)
                                download_count += 1

                                # 3. Fallback Gemini AI Job Classification if subject tag was missing
                                if not matched_job_id and active_jobs:
                                    print("-> No subject tag found. Using Gemini AI to classify target job opening...")
                                    matched_job_id = match_email_to_job_with_gemini(
                                        subject=subject,
                                        email_body=email_body,
                                        resume_snippet=resume_text[:1000],
                                        active_jobs=active_jobs
                                    )

                                # Save candidate record to database if DB session is active & matched job ID exists
                                if db_session and matched_job_id:
                                    from models import Candidate
                                    try:
                                        # Extract real applicant email address
                                        candidate_email = ""
                                        if "<" in sender and ">" in sender:
                                            candidate_email = sender.split("<")[1].split(">")[0].strip()
                                        elif "@" in sender:
                                            candidate_email = sender.strip('" ')
                                        
                                        if not candidate_email:
                                            candidate_email = email_user

                                        # Clean candidate name (strip quotes, email, and words like Resume/CV)
                                        raw_name = sender.split("<")[0].strip('" ').strip()
                                        if not raw_name or "@" in raw_name:
                                            raw_name = safe_filename.replace(".pdf", "").replace(".PDF", "")
                                        
                                        # Remove common file artifacts from name
                                        for artifact in ["Resume", "resume", "CV", "cv", "Academic", "academic", "Portfolio", "portfolio", "_", "-"]:
                                            raw_name = raw_name.replace(artifact, " ")
                                        candidate_name = " ".join(raw_name.split()).title() or "Applicant"

                                        candidate = Candidate(
                                            job_id=matched_job_id,
                                            name=candidate_name,
                                            email=candidate_email,
                                            resume_path=filepath,
                                            parsed_text=resume_text,
                                            email_body=email_body,
                                            status="Applied"
                                        )
                                        db_session.add(candidate)
                                        db_session.commit()
                                        print(f"-> Saved candidate '{candidate_name}' ({candidate_email}) to DB for job [{matched_job_id}]")
                                    except Exception as db_err:
                                        db_session.rollback()
                                        print(f"Error saving candidate to DB: {db_err}")

                    # Mark email as read
                    mail.store(mail_id, '+FLAGS', '\\Seen')
        except Exception as ex:
            print(f"Error processing email ID {mail_id}: {ex}")

    print("\n" + "=" * 50)
    print(f"FINISHED: Downloaded {download_count} resume(s) to folder: {save_dir}")
    print("=" * 50)

    try:
        mail.close()
        mail.logout()
    except Exception:
        pass
    
    return download_count

def main():
    sync_resumes_from_email()

if __name__ == "__main__":
    main()
