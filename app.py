import os
import sys
import time
import subprocess
import threading
import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
import customtkinter as ctk
import pdfplumber
import uvicorn
from google import genai
from dotenv import load_dotenv
from database import SessionLocal

# Load .env explicitly and override any existing environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path, override=True)

# Force stdout/stderr to use UTF-8 encoding (prevents Windows Unicode print crashes)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Gemini API setup & Memory Config ────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    GEMINI_API_KEY = GEMINI_API_KEY.strip('"' + "'").strip()

# Memory configuration fields loaded from .env
COMPANY_NAME  = os.environ.get("COMPANY_NAME", "").strip('"' + "'").strip()
COMPANY_INTRO = os.environ.get("COMPANY_INTRO", "").strip('"' + "'").strip()
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "").strip('"' + "'").strip()

def refine_with_gemini(raw_text: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here" or not GEMINI_API_KEY.strip():
        return raw_text

    # Build context memory block
    memory_context = ""
    if COMPANY_NAME:
        memory_context += f"- Company Name: {COMPANY_NAME}\n"
    if COMPANY_INTRO:
        memory_context += f"- Company Intro: {COMPANY_INTRO}\n"
    if CONTACT_EMAIL:
        memory_context += f"- Apply Contact Email: {CONTACT_EMAIL}\n"

    prompt = f"""You are a professional LinkedIn content writer.
Refine the following rough job posting or LinkedIn post draft into a polished, 
engaging, and professional LinkedIn post. Use appropriate formatting 
(headings, bullet points, emojis where suitable). Keep it concise yet complete.

Here is the hiring company context and contact details to include in the post:
{memory_context}

Return ONLY the final post text — no explanations, no preamble. Do not leave placeholder text like "[Insert Email]".

Draft:
{raw_text}"""

    models_to_try = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash-cyber",
        "gemini-2.5-pro",
        "gemini-3.5-flash"
    ]

    for model_name in models_to_try:
        for attempt in range(3):
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return response.text.strip()
            except Exception:
                time.sleep(1.5)

    return raw_text

def apply_feedback_with_gemini(current_text: str, feedback: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here" or not GEMINI_API_KEY.strip():
        return current_text

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        memory_context = ""
        if COMPANY_NAME:
            memory_context += f"- Company Name: {COMPANY_NAME}\n"
        if COMPANY_INTRO:
            memory_context += f"- Company Intro: {COMPANY_INTRO}\n"
        if CONTACT_EMAIL:
            memory_context += f"- Apply Contact Email: {CONTACT_EMAIL}\n"

        prompt = f"""You are a professional LinkedIn content editor.
Below is the current draft of a LinkedIn post, followed by instructions from the user on what to change.
Modify the post content to exactly match the user's instructions. Keep the professional formatting, bullet points, and appropriate emojis.

Make sure to preserve or incorporate the following hiring company details if they are relevant:
{memory_context}

Return ONLY the updated post text — no explanations, no preamble. Do not leave placeholder text like "[Insert Email]".

Current Post Draft:
{current_text}

User's Modification Instructions:
{feedback}"""
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception:
        return current_text

def get_linkedin_app_window(desktop):
    """
    Finds the native LinkedIn UWP app window.
    Filters out web browsers (like Chrome or Firefox) containing 'LinkedIn' in the title.
    """
    for win in desktop.windows():
        try:
            title = win.window_text()
            cls = win.class_name()
            # UWP app window has title exactly "LinkedIn" and class "ApplicationFrameWindow"
            if title == "LinkedIn" and cls == "ApplicationFrameWindow":
                return desktop.window(handle=win.handle)
        except Exception:
            continue
    # Fallback 1: exact title "LinkedIn"
    for win in desktop.windows():
        try:
            if win.window_text() == "LinkedIn":
                return desktop.window(handle=win.handle)
        except Exception:
            continue
    # Fallback 2: contains "LinkedIn" but is not a browser window
    for win in desktop.windows():
        try:
            title = win.window_text()
            cls = win.class_name()
            if "LinkedIn" in title and cls not in ["Chrome_WidgetWin_1", "MozillaWindowClass", "CabinetWClass"]:
                return desktop.window(handle=win.handle)
        except Exception:
            continue
    return None

def transcribe_audio_with_gemini(filepath: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here" or not GEMINI_API_KEY.strip():
        return "Error: Gemini API Key not set."

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Upload the audio file to GenAI File API
        print(f"[Gemini] Uploading voice recording: {filepath}")
        uploaded_file = client.files.upload(file=filepath)
        
        # Wait for file processing state to clear
        state = uploaded_file.state
        attempts = 0
        while state == "PROCESSING" and attempts < 10:
            time.sleep(1)
            uploaded_file = client.files.get(name=uploaded_file.name)
            state = uploaded_file.state
            attempts += 1
            
        if state == "FAILED":
            return "Error: Gemini audio processing failed."

        print("[Gemini] Requesting transcription output...")
        
        models_to_try = [
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash-cyber",
            "gemini-2.5-pro",
            "gemini-3.5-flash"
        ]

        transcription_text = None
        last_error = None

        for model_name in models_to_try:
            for attempt in range(2):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            uploaded_file,
                            "Transcribe this audio recording exactly. Do not add any preamble, explanation, or summary. Return only the transcription text."
                        ]
                    )
                    transcription_text = response.text.strip()
                    break
                except Exception as e:
                    last_error = e
                    time.sleep(1.5)
            if transcription_text is not None:
                break
        
        # Cleanup uploaded file from the cloud
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass

        if transcription_text is not None:
            return transcription_text
        else:
            return f"Error during transcription: {last_error}"
    except Exception as e:
        return f"Error during transcription: {e}"

# ── GUI Application ──────────────────────────────────────────────────────────
class LinkedInBotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("LinkedIn Post Assistant")
        self.geometry("1250x650")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Recording state variables
        self.is_recording = False
        self.audio_q = queue.Queue()
        self.audio_stream = None
        self.recording_timer = 0
        self.selected_job_id = None

        # Initialize SQLite database file immediately at startup
        import database
        try:
            database.init_db()
            print("Database initialized successfully.")
        except Exception as db_init_err:
            print(f"Error initializing DB: {db_init_err}")

        # Start local FastAPI server in background thread
        threading.Thread(target=self.run_backend_server, daemon=True).start()

        # Configure grid layout (1 row, 3 columns)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=4) # Left Panel: Input & Controls
        self.grid_columnconfigure(1, weight=4) # Middle Panel: Preview
        self.grid_columnconfigure(2, weight=3) # Right Panel: Resumes

        # Left Panel Frame
        self.left_frame = ctk.CTkFrame(self, corner_radius=0)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.left_frame.grid_rowconfigure(1, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)

        # Middle Panel Frame (formerly Right Frame)
        self.right_frame = ctk.CTkFrame(self, corner_radius=0)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Rightmost Panel Frame (Resumes)
        self.resumes_frame = ctk.CTkFrame(self, corner_radius=0)
        self.resumes_frame.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)
        self.resumes_frame.grid_rowconfigure(1, weight=1)
        self.resumes_frame.grid_columnconfigure(0, weight=1)

        # ── Left Panel Widgets ──
        self.left_title = ctk.CTkLabel(
            self.left_frame, 
            text="Describe Job or Changes", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.left_title.grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        self.placeholder_text = "Enter your job description prompt or voice input changes here..."
        self.input_textbox = ctk.CTkTextbox(self.left_frame, height=350)
        self.input_textbox.grid(row=1, column=0, sticky="nsew", padx=15, pady=5)
        self.input_textbox.insert("1.0", self.placeholder_text)
        self.input_textbox.configure(text_color="#888888")

        # Bind placeholder focus events
        self.input_textbox.bind("<FocusIn>", self.clear_placeholder)
        self.input_textbox.bind("<FocusOut>", self.restore_placeholder)

        # Controls panel for Voice and Action buttons
        self.controls_panel = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.controls_panel.grid(row=2, column=0, sticky="ew", padx=15, pady=10)
        self.controls_panel.columnconfigure(0, weight=1)
        self.controls_panel.columnconfigure(1, weight=1)

        self.voice_btn = ctk.CTkButton(
            self.controls_panel, 
            text="🎤 Record Voice Input", 
            command=self.toggle_recording,
            fg_color="#3e4555",
            hover_color="#535c70"
        )
        self.voice_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.action_btn = ctk.CTkButton(
            self.controls_panel, 
            text="Generate Job Description", 
            command=self.handle_action
        )
        self.action_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # Status Label
        self.status_label = ctk.CTkLabel(
            self.left_frame, 
            text="Ready", 
            text_color="#888888",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=3, column=0, sticky="sw", padx=15, pady=(5, 10))

        # ── Right Panel Widgets ──
        self.right_title = ctk.CTkLabel(
            self.right_frame, 
            text="LinkedIn Post Preview", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.right_title.grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        self.preview_textbox = ctk.CTkTextbox(self.right_frame)
        self.preview_textbox.grid(row=1, column=0, sticky="nsew", padx=15, pady=5)
        self.preview_textbox.insert("1.0", "Polished text will appear here...")
        self.preview_textbox.configure(state="disabled")

        # Bottom Button Panel inside Right Frame (3 Columns)
        self.button_panel = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.button_panel.grid(row=2, column=0, sticky="ew", padx=15, pady=15)
        self.button_panel.columnconfigure(0, weight=1)
        self.button_panel.columnconfigure(1, weight=1)
        self.button_panel.columnconfigure(2, weight=1)

        self.cancel_btn = ctk.CTkButton(
            self.button_panel, 
            text="Clear / Cancel", 
            command=self.clear_all,
            fg_color="#a83232",
            hover_color="#c93e3e"
        )
        self.cancel_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.download_btn = ctk.CTkButton(
            self.button_panel, 
            text="📥 Download Resumes", 
            command=self.start_downloading_resumes,
            fg_color="#3e4555",
            hover_color="#535c70"
        )
        self.download_btn.grid(row=0, column=1, padx=5, sticky="ew")

        self.publish_btn = ctk.CTkButton(
            self.button_panel, 
            text="Approve & Publish", 
            command=self.start_publishing,
            fg_color="#2b6b3b",
            hover_color="#368c4c",
            state="disabled"
        )
        self.publish_btn.grid(row=0, column=2, padx=(5, 0), sticky="ew")

        # ── Resumes Panel Widgets (Column 2) ──
        self.resumes_title = ctk.CTkLabel(
            self.resumes_frame, 
            text="Candidates & Scoring", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.resumes_title.grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        # Job selection dropdown filter
        self.job_select_lbl = ctk.CTkLabel(
            self.resumes_frame, 
            text="Select Job Position:", 
            font=ctk.CTkFont(size=12)
        )
        self.job_select_lbl.grid(row=1, column=0, sticky="w", padx=15, pady=(5, 2))

        self.job_select_menu = ctk.CTkOptionMenu(
            self.resumes_frame, 
            values=["All (Local Folder Only)"],
            command=self.on_job_selected
        )
        self.job_select_menu.grid(row=2, column=0, sticky="ew", padx=15, pady=(2, 10))

        self.resumes_scroll = ctk.CTkScrollableFrame(self.resumes_frame)
        self.resumes_scroll.grid(row=3, column=0, sticky="nsew", padx=15, pady=5)

        # Resumes Panel Control buttons (Sync / Score / Reload)
        self.resumes_btn_panel = ctk.CTkFrame(self.resumes_frame, fg_color="transparent")
        self.resumes_btn_panel.grid(row=4, column=0, sticky="ew", padx=15, pady=15)
        self.resumes_btn_panel.columnconfigure(0, weight=1)
        self.resumes_btn_panel.columnconfigure(1, weight=1)
        self.resumes_btn_panel.columnconfigure(2, weight=1)

        self.resumes_sync_btn = ctk.CTkButton(
            self.resumes_btn_panel,
            text="Sync",
            command=self.start_downloading_resumes,
            fg_color="#3e4555",
            hover_color="#535c70"
        )
        self.resumes_sync_btn.grid(row=0, column=0, padx=(0, 2), sticky="ew")

        self.resumes_score_btn = ctk.CTkButton(
            self.resumes_btn_panel,
            text="Score",
            command=self.start_scoring_candidates,
            fg_color="#2b6b3b",
            hover_color="#368c4c",
            state="disabled"
        )
        self.resumes_score_btn.grid(row=0, column=1, padx=2, sticky="ew")

        self.resumes_refresh_btn = ctk.CTkButton(
            self.resumes_btn_panel,
            text="Reload",
            command=self.refresh_resume_list,
            fg_color="#3e4555",
            hover_color="#535c70"
        )
        self.resumes_refresh_btn.grid(row=0, column=2, padx=(2, 0), sticky="ew")

        # Load active jobs dropdown list
        self.load_jobs_into_dropdown()

        # Load list initial values
        self.refresh_resume_list()

    # ── Button Command Thread Actions ──
    def update_status(self, text, color="#888888"):
        self.status_label.configure(text=text, text_color=color)

    def set_widgets_state(self, state):
        self.action_btn.configure(state=state)
        self.voice_btn.configure(state=state)
        self.download_btn.configure(state=state)
        self.publish_btn.configure(state=state if self.preview_textbox.get("1.0", "end-1c") not in ["", "Polished text will appear here..."] else "disabled")
        self.cancel_btn.configure(state=state)
        self.resumes_sync_btn.configure(state=state)
        self.resumes_refresh_btn.configure(state=state)
        self.job_select_menu.configure(state=state)
        if state == "normal" and self.selected_job_id:
            self.resumes_score_btn.configure(state="normal")
        else:
            self.resumes_score_btn.configure(state="disabled")

    def handle_action(self):
        preview_content = self.preview_textbox.get("1.0", "end-1c").strip()
        if not preview_content or preview_content == "Polished text will appear here...":
            self.start_generation()
        else:
            self.start_refinement()

    # 0. Resume Downloader Workflow
    def start_downloading_resumes(self):
        self.update_status("Connecting to Gmail and searching for resumes...", "#3b8ed0")
        self.set_widgets_state("disabled")

        threading.Thread(target=self._run_download_resumes, daemon=True).start()

    def _run_download_resumes(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(script_dir, "download_resumes.py")
            
            # Execute downloader script in the background
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            
            # Log output to background CLI for debugging
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            
            # Parse number of downloaded resumes from result text
            count = 0
            for line in result.stdout.split("\n"):
                if "FINISHED: Downloaded" in line:
                    parts = line.split("Downloaded")
                    if len(parts) > 1:
                        num_part = parts[1].strip().split()[0]
                        try:
                            count = int(num_part)
                        except ValueError:
                            pass

            if result.returncode == 0:
                self.after(0, lambda: self.finish_download_resumes(f"Successfully downloaded {count} new resume(s)!"))
            else:
                # Look for configuration errors
                error_msg = "Error: Check credentials or App Password."
                if "configured in .env file" in result.stdout:
                    error_msg = "Error: GMAIL_APP_PASSWORD missing from .env."
                self.after(0, lambda: self.finish_download_resumes(error_msg, error=True))
        except Exception as e:
            self.after(0, lambda: self.finish_download_resumes(f"Error: {e}", error=True))

    def finish_download_resumes(self, msg, error=False):
        self.set_widgets_state("normal")
        color = "#a83232" if error else "#2b6b3b"
        self.update_status(msg, color)
        # Refresh lists immediately
        self.refresh_resume_list()

    # 1. Generation Workflow
    def start_generation(self):
        raw_text = self.input_textbox.get("1.0", "end-1c").strip()
        if not raw_text or raw_text == self.placeholder_text:
            self.update_status("Error: Input prompt cannot be empty.", "#c93e3e")
            return

        self.update_status("Calling Gemini API to generate post...", "#3b8ed0")
        self.set_widgets_state("disabled")
        
        threading.Thread(target=self._run_generation, args=(raw_text,), daemon=True).start()

    def _run_generation(self, raw_text):
        refined = refine_with_gemini(raw_text)
        self.after(0, lambda: self.finish_generation(refined))

    def finish_generation(self, refined):
        self.preview_textbox.configure(state="normal")
        self.preview_textbox.delete("1.0", "end")
        self.preview_textbox.insert("1.0", refined)
        self.preview_textbox.configure(state="normal")

        self.action_btn.configure(text="Update / Refine Post")
        self.input_textbox.delete("1.0", "end")
        self.set_widgets_state("normal")
        self.update_status("Generation complete!", "#2b6b3b")

    # 2. Refinement Workflow
    def start_refinement(self):
        current_text = self.preview_textbox.get("1.0", "end-1c").strip()
        feedback = self.input_textbox.get("1.0", "end-1c").strip()
        if not feedback or feedback == self.placeholder_text:
            self.update_status("Error: Feedback instructions cannot be empty.", "#c93e3e")
            return

        self.update_status("Applying changes with Gemini...", "#3b8ed0")
        self.set_widgets_state("disabled")

        threading.Thread(target=self._run_refinement, args=(current_text, feedback), daemon=True).start()

    def _run_refinement(self, current_text, feedback):
        updated = apply_feedback_with_gemini(current_text, feedback)
        self.after(0, lambda: self.finish_refinement(updated))

    def finish_refinement(self, updated):
        self.preview_textbox.configure(state="normal")
        self.preview_textbox.delete("1.0", "end")
        self.preview_textbox.insert("1.0", updated)
        
        self.input_textbox.delete("1.0", "end")
        self.set_widgets_state("normal")
        self.update_status("Changes applied successfully!", "#2b6b3b")

    # 3. Clipboard + Native App Publishing Workflow
    def start_publishing(self):
        refined_text = self.preview_textbox.get("1.0", "end-1c").strip()
        
        # Prompt user to input Job Title for tracking (main thread UI block)
        from tkinter import simpledialog
        job_title = simpledialog.askstring("Track Job", "Enter a Job Title to save this post in the database:\n(e.g., Data Scientist - Leave blank to skip tracking)")

        self.update_status("Saving job, copying to clipboard & launching LinkedIn...", "#3b8ed0")
        self.set_widgets_state("disabled")

        threading.Thread(target=self._run_publishing, args=(refined_text, job_title), daemon=True).start()

    def _run_publishing(self, refined_text, job_title):
        # Save to database if a title is entered
        if job_title:
            db = SessionLocal()
            try:
                from server import create_job, JobCreate
                job_data = JobCreate(title=job_title, description=refined_text)
                db_job = create_job(job_data, db)
                # Override clipboard with text containing generated apply tag instructions
                refined_text = db_job.description
                print(f"Created tracked Job in database: {db_job.job_id}")

                # Refresh dropdown in main thread UI
                self.after(0, self.load_jobs_into_dropdown)
                self.after(0, lambda: self.job_select_menu.set(f"{db_job.job_id} - {db_job.title}"))
                self.after(0, lambda: self.on_job_selected(f"{db_job.job_id} - {db_job.title}"))
            except Exception as db_err:
                print(f"Database job creation failed: {db_err}")
            finally:
                db.close()

        # Copy description to clipboard (will be pasted into job description field)
        import pyperclip
        try:
            pyperclip.copy(refined_text)
            print("[Clipboard] Copied successfully.")
        except Exception as e:
            print(f"[Clipboard] Failed: {e}")

        # Launch LinkedIn PWA app
        app_id = "7EE7776C.LinkedInforWindows_w1wdnht996qgy!App"
        try:
            subprocess.Popen(
                ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"Error launching: {e}")

        # Wait for window to open and bring to focus
        time.sleep(5)
        focused_success = False

        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        app_win = get_linkedin_app_window(desktop)

        if app_win:
            try:
                if app_win.is_minimized():
                    app_win.restore()
                app_win.set_focus()
                print("LinkedIn window brought to focus!")
                focused_success = True
            except Exception as e:
                print(f"Failed to focus LinkedIn window: {e}")
        else:
            print("Note: Could not automatically locate the LinkedIn app window.")

        # ── NEW FLOW: Jobs tab → Post a job ──
        # LinkedIn Windows App top navigation: Home | My Network | Jobs | Messaging | Notifications | Me
        navigated = False
        if focused_success and app_win:
            try:
                print("[Bot] Starting navigation: Looking for 'Jobs' button in top navigation bar...")
                
                # Step 1: Click the "Jobs" button/icon (briefcase icon) in the top navigation bar
                jobs_btn = None
                
                # Try various title patterns for the Jobs button
                for title_try in ["Jobs", "Jobs ", "Jobs▾", "Job"]:
                    try:
                        candidate = app_win.child_window(title=title_try, control_type="Button")
                        if candidate.exists(timeout=3):
                            jobs_btn = candidate
                            print(f"[Bot] Found 'Jobs' button with title: '{title_try}'")
                            break
                    except Exception:
                        pass
                
                # Additional fallback: look for briefcase icon / navigation item
                if jobs_btn is None:
                    for ctrl_type in ["Button", "TabItem", "ListItem", "Hyperlink"]:
                        try:
                            candidate = app_win.child_window(title_re=".*[Jj]ob.*", control_type=ctrl_type)
                            if candidate.exists(timeout=2):
                                jobs_btn = candidate
                                print(f"[Bot] Found 'Jobs' navigation item as {ctrl_type}")
                                break
                        except Exception:
                            pass
                
                if jobs_btn and jobs_btn.exists():
                    jobs_btn.click_input()
                    print("[Bot] ✅ Clicked 'Jobs' button in top navigation bar.")
                    time.sleep(3)  # Wait for Jobs view to load
                    
                    # Step 2: Once in Jobs view, find and click "Post a job" or "Post a job for free" button
                    post_job_btn = None
                    
                    # Try exact title matches first
                    for title_try in [
                        "Post a job for free", 
                        "Post a Job for Free",
                        "Post a job",
                        "Post a Job",
                        "Post job",
                        "Post Job"
                    ]:
                        try:
                            candidate = app_win.child_window(title=title_try, control_type="Button")
                            if candidate.exists(timeout=4):
                                post_job_btn = candidate
                                print(f"[Bot] Found 'Post a job' button with title: '{title_try}'")
                                break
                        except Exception:
                            pass
                    
                    # Fallback: broader search for any button/link containing 'post a job' or 'post job'
                    if post_job_btn is None:
                        for ctrl_type in ["Button", "Hyperlink", "ListItem", "Text"]:
                            try:
                                candidate = app_win.child_window(title_re=".*[Pp]ost.*[Jj]ob.*", control_type=ctrl_type)
                                if candidate.exists(timeout=3):
                                    post_job_btn = candidate
                                    print(f"[Bot] Found 'Post a job' button as {ctrl_type} via regex")
                                    break
                            except Exception:
                                pass
                    
                    # Additional fallback: look for "Post a job for free" specifically
                    if post_job_btn is None:
                        for ctrl_type in ["Button", "Hyperlink", "ListItem", "Text"]:
                            try:
                                candidate = app_win.child_window(title_re=".*[Pp]ost.*[Jj]ob.*[Ff]ree.*", control_type=ctrl_type)
                                if candidate.exists(timeout=2):
                                    post_job_btn = candidate
                                    print(f"[Bot] Found 'Post a job for free' as {ctrl_type} via regex")
                                    break
                            except Exception:
                                pass
                    
                    if post_job_btn and post_job_btn.exists():
                        post_job_btn.click_input()
                        print("[Bot] ✅ Clicked 'Post a job' button. Job creation form should open now.")
                        navigated = True
                        time.sleep(5)  # Wait for job form to fully load
                    else:
                        print("[Bot] ⚠️ Could not find 'Post a job' button — please click it manually in the Jobs tab.")
                        print("[Bot] Looking for buttons with titles like: 'Post a job', 'Post a job for free', 'Post Job'")
                else:
                    print("[Bot] ⚠️ Could not find 'Jobs' button in top navigation bar.")
                    print("[Bot] Top nav should have: Home | My Network | Jobs | Messaging | Notifications | Me")
                    print("[Bot] Please click 'Jobs' manually, then 'Post a job'.")
                    
            except Exception as e:
                print(f"[Bot] Navigation error: {e}")
                import traceback
                traceback.print_exc()

        if not navigated:
            print("[Bot] Automatic navigation failed. Waiting 10 seconds for you to navigate manually to the job posting form...")
            time.sleep(10)

        # Launch the AI vision bot (post_playwright.py) in a visible terminal
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            publish_bot_path = os.path.join(script_dir, "post_playwright.py")
            subprocess.Popen(["cmd", "/k", sys.executable, publish_bot_path])
        except Exception as e:
            print(f"Error launching AI vision bot: {e}")

        self.after(0, self.finish_publishing)

    def finish_publishing(self):
        self.set_widgets_state("normal")
        self.update_status("AI Vision Bot launched — watch the terminal for live progress!", "#2b6b3b")

    # 4. Clear/Cancel action
    def clear_all(self):
        self.preview_textbox.configure(state="normal")
        self.preview_textbox.delete("1.0", "end")
        self.preview_textbox.insert("1.0", "Polished text will appear here...")
        self.preview_textbox.configure(state="disabled")

        self.input_textbox.delete("1.0", "end")
        self.input_textbox.insert("1.0", self.placeholder_text)
        self.input_textbox.configure(text_color="#888888")

        self.action_btn.configure(text="Generate Job Description")
        self.set_widgets_state("normal")
        self.update_status("Cleared", "#888888")

    # 5. Microphone Recording & Transcription Commands
    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.is_recording = True
        self.audio_q = queue.Queue()
        self.recording_timer = 0
        
        self.voice_btn.configure(text="🛑 Stop Recording (0s)", fg_color="#a83232", hover_color="#c93e3e")
        self.update_status("Recording microphone input...", "#3b8ed0")
        
        self.set_widgets_state("disabled")
        self.voice_btn.configure(state="normal") # Keep record button active to stop

        def callback(indata, frames, time_info, status):
            if status:
                print(status, file=sys.stderr)
            self.audio_q.put(indata.copy())

        try:
            self.audio_stream = sd.InputStream(samplerate=44100, channels=1, callback=callback)
            self.audio_stream.start()
            self.tick_timer()
        except Exception as e:
            self.is_recording = False
            self.update_status(f"Error opening mic: {e}", "#a83232")
            self.voice_btn.configure(text="🎤 Record Voice Input", fg_color="#3e4555", hover_color="#535c70")
            self.set_widgets_state("normal")

    def tick_timer(self):
        if self.is_recording:
            self.recording_timer += 1
            self.voice_btn.configure(text=f"🛑 Stop Recording ({self.recording_timer}s)")
            self.after(1000, self.tick_timer)

    def stop_recording(self):
        if not self.is_recording:
            return
        
        self.is_recording = False
        self.update_status("Saving audio file...", "#3b8ed0")
        
        try:
            if self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
        except Exception as e:
            print(f"Error closing recording stream: {e}")

        self.voice_btn.configure(text="🎤 Record Voice Input", fg_color="#3e4555", hover_color="#535c70")
        threading.Thread(target=self._save_and_transcribe, daemon=True).start()

    def _save_and_transcribe(self):
        filename = "temp_voice_input.wav"
        
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                pass
                
        try:
            frames = []
            while not self.audio_q.empty():
                frames.append(self.audio_q.get())
                
            if len(frames) == 0:
                self.after(0, lambda: self.finish_transcription("Error: No audio recorded."))
                return

            audio_data = np.concatenate(frames, axis=0)
            sf.write(filename, audio_data, 44100)
            
            self.after(0, lambda: self.update_status("Uploading audio to Gemini for transcribing...", "#3b8ed0"))
            transcription = transcribe_audio_with_gemini(filename)
            self.after(0, lambda: self.finish_transcription(transcription))
        except Exception as e:
            self.after(0, lambda: self.finish_transcription(f"Error saving audio: {e}"))
        finally:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass

    def finish_transcription(self, transcription):
        self.set_widgets_state("normal")
        
        if transcription.startswith("Error:"):
            self.update_status(transcription, "#a83232")
            return
            
        # Clear placeholder if present
        self.clear_placeholder()
            
        current_text = self.input_textbox.get("1.0", "end-1c").strip()
        if current_text:
            new_text = current_text + " " + transcription
        else:
            new_text = transcription
            
        self.input_textbox.delete("1.0", "end")
        self.input_textbox.insert("1.0", new_text)
        self.input_textbox.configure(text_color="#ffffff")
        self.update_status("Voice transcribed successfully!", "#2b6b3b")

    # Placeholder Helpers
    def clear_placeholder(self, event=None):
        current_val = self.input_textbox.get("1.0", "end-1c").strip()
        if current_val == self.placeholder_text:
            self.input_textbox.delete("1.0", "end")
            self.input_textbox.configure(text_color="#ffffff")

    def restore_placeholder(self, event=None):
        current_val = self.input_textbox.get("1.0", "end-1c").strip()
        if not current_val:
            self.input_textbox.insert("1.0", self.placeholder_text)
            self.input_textbox.configure(text_color="#888888")

    # ── FastAPI Background Server ──
    def run_backend_server(self):
        try:
            from server import app as fastapi_app
            uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="warning")
        except Exception as e:
            print(f"Error starting backend FastAPI server: {e}")

    # ── Job Selection dropdown Management ──
    def load_jobs_into_dropdown(self):
        db = SessionLocal()
        try:
            from models import Job
            jobs = db.query(Job).order_by(Job.created_at.desc()).all()
            
            # Format values
            options = ["All (Local Folder Only)"]
            for job in jobs:
                options.append(f"{job.job_id} - {job.title}")
            
            self.job_select_menu.configure(values=options)
            
            # Keep select value consistent
            current_val = self.job_select_menu.get()
            if current_val not in options:
                self.job_select_menu.set(options[0])
                self.selected_job_id = None
        except Exception as e:
            print(f"Error reading jobs for dropdown: {e}")
        finally:
            db.close()

    def on_job_selected(self, selected_value):
        if selected_value == "All (Local Folder Only)":
            self.selected_job_id = None
            self.resumes_score_btn.configure(state="disabled")
        else:
            # Extract ID from 'ARG-JD-001 - Title'
            self.selected_job_id = selected_value.split(" - ")[0].strip()
            self.resumes_score_btn.configure(state="normal")
            
        self.refresh_resume_list()

    # ── Candidate Scoring Workflow ──
    def start_scoring_candidates(self):
        if not self.selected_job_id:
            return
        self.update_status("Evaluating resumes using Gemini...", "#3b8ed0")
        self.set_widgets_state("disabled")
        self.resumes_score_btn.configure(state="disabled")
        
        threading.Thread(target=self._run_scoring_candidates, daemon=True).start()

    def _run_scoring_candidates(self):
        try:
            db = SessionLocal()
            try:
                from server import score_candidates
                res = score_candidates(self.selected_job_id, db)
                count = res.get("scored_count", 0)
                self.after(0, lambda: self.finish_scoring_candidates(f"Successfully scored {count} candidate(s)!"))
            finally:
                db.close()
        except Exception as e:
            self.after(0, lambda: self.finish_scoring_candidates(f"Error during scoring: {e}", error=True))

    def finish_scoring_candidates(self, msg, error=False):
        self.set_widgets_state("normal")
        color = "#a83232" if error else "#2b6b3b"
        self.update_status(msg, color)
        self.refresh_resume_list()

    # ── Resumes Directory Management ──
    def refresh_resume_list(self):
        # Clear existing items in scrollable frame
        for widget in self.resumes_scroll.winfo_children():
            widget.destroy()

        resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
        if not os.path.exists(resumes_dir):
            try:
                os.makedirs(resumes_dir)
            except Exception:
                return

        # Fetch resumes and layout based on mode (All files vs Job-specific candidates)
        if self.selected_job_id is None:
            # Mode A: Display all files inside resumes folder
            files = [f for f in os.listdir(resumes_dir) if f.lower().endswith(".pdf")]
            if not files:
                empty_lbl = ctk.CTkLabel(self.resumes_scroll, text="No resumes found.", text_color="#888888")
                empty_lbl.grid(row=0, column=0, padx=10, pady=10, sticky="w")
                return

            # Auto-convert missing .txt files
            for filename in files:
                pdf_path = os.path.join(resumes_dir, filename)
                base_name, _ = os.path.splitext(filename)
                txt_path = os.path.join(resumes_dir, base_name + ".txt")
                if not os.path.exists(txt_path):
                    try:
                        text_content = []
                        with pdfplumber.open(pdf_path) as pdf:
                            for page_idx, page in enumerate(pdf.pages):
                                page_text = page.extract_text()
                                if page_text:
                                    text_content.append(page_text)
                                else:
                                    text_content.append(f"[Page {page_idx+1}: Empty/Image]")
                        
                        full_text = "\n\n--- PAGE BREAK ---\n\n".join(text_content).strip()
                        with open(txt_path, "w", encoding="utf-8") as f:
                            f.write(full_text)
                    except Exception as e:
                        print(f"Error auto-converting {filename}: {e}")

            for idx, filename in enumerate(sorted(files)):
                row_frame = ctk.CTkFrame(self.resumes_scroll, fg_color="transparent")
                row_frame.grid(row=idx, column=0, sticky="ew", pady=5, padx=2)
                row_frame.columnconfigure(0, weight=1)

                display_name = filename
                if len(display_name) > 22:
                    display_name = display_name[:19] + "..."

                lbl = ctk.CTkLabel(row_frame, text=display_name, anchor="w")
                lbl.grid(row=0, column=0, sticky="w", padx=(5, 10))
                lbl.bind("<Double-Button-1>", lambda e, fn=filename: self.open_resume(fn))

                open_btn = ctk.CTkButton(row_frame, text="Open", width=50, height=24,
                                         command=lambda fn=filename: self.open_resume(fn),
                                         fg_color="#2b6b3b", hover_color="#368c4c")
                open_btn.grid(row=0, column=1, padx=2)

                del_btn = ctk.CTkButton(row_frame, text="Del", width=45, height=24,
                                        command=lambda fn=filename: self.delete_resume(fn),
                                        fg_color="#a83232", hover_color="#c93e3e")
                del_btn.grid(row=0, column=2, padx=2)

        else:
            # Mode B: Query candidate database objects linked to selected job_id
            db = SessionLocal()
            try:
                from models import Candidate
                candidates = db.query(Candidate).filter(Candidate.job_id == self.selected_job_id).order_by(Candidate.relevance_score.desc()).all()
                
                if not candidates:
                    empty_lbl = ctk.CTkLabel(self.resumes_scroll, text="No applicants yet.", text_color="#888888")
                    empty_lbl.grid(row=0, column=0, padx=10, pady=10, sticky="w")
                    return

                for idx, cand in enumerate(candidates):
                    row_frame = ctk.CTkFrame(self.resumes_scroll, fg_color="transparent")
                    row_frame.grid(row=idx, column=0, sticky="ew", pady=5, padx=2)
                    row_frame.columnconfigure(0, weight=1)

                    # Build info text: "Name - Score%"
                    score_info = "Applied"
                    if cand.relevance_score is not None:
                        score_info = f"{cand.relevance_score}%"

                    display_name = f"{cand.name} ({score_info})"
                    if len(display_name) > 22:
                        display_name = display_name[:19] + "..."

                    lbl = ctk.CTkLabel(row_frame, text=display_name, anchor="w")
                    lbl.grid(row=0, column=0, sticky="w", padx=(5, 10))
                    
                    # Double click details check
                    lbl.bind("<Double-Button-1>", lambda e, c=cand: self.show_candidate_details(c))

                    filename = os.path.basename(cand.resume_path)
                    open_btn = ctk.CTkButton(row_frame, text="Open", width=50, height=24,
                                             command=lambda fn=filename: self.open_resume(fn),
                                             fg_color="#2b6b3b", hover_color="#368c4c")
                    open_btn.grid(row=0, column=1, padx=2)

                    del_btn = ctk.CTkButton(row_frame, text="Del", width=45, height=24,
                                            command=lambda cid=cand.candidate_id: self.delete_candidate_by_id(cid),
                                            fg_color="#a83232", hover_color="#c93e3e")
                    del_btn.grid(row=0, column=2, padx=2)

            except Exception as e:
                print(f"Error querying candidates: {e}")
            finally:
                db.close()

    def show_candidate_details(self, cand):
        # Open a messagebox popup showing full evaluation details
        from tkinter import messagebox
        title = f"Candidate Evaluation: {cand.name}"
        score = f"{cand.relevance_score}%" if cand.relevance_score is not None else "Not Scored"
        rec = getattr(cand, "recommendation", None) or "N/A"
        
        skills = getattr(cand, "skills_score", None)
        exp = getattr(cand, "experience_score", None)
        edu = getattr(cand, "education_score", None)
        loc = getattr(cand, "location_score", None)
        
        breakdown = ""
        if any(v is not None for v in [skills, exp, edu, loc]):
            breakdown = f"\nScore Breakdown:\n- Skills Match: {skills if skills is not None else 'N/A'}/35\n- Experience Match: {exp if exp is not None else 'N/A'}/35\n- Education: {edu if edu is not None else 'N/A'}/15\n- Location & Fit: {loc if loc is not None else 'N/A'}/15\n"

        strengths_str = getattr(cand, "strengths", "") or ""
        gaps_str = getattr(cand, "gaps", "") or ""
        
        extra = ""
        if strengths_str:
            extra += f"\nStrengths:\n{strengths_str}\n"
        if gaps_str:
            extra += f"\nGaps / Missing:\n{gaps_str}\n"

        details = f"Candidate: {cand.name}\nEmail: {cand.email}\nStatus: {cand.status}\nTotal Score: {score} [{rec}]\n{breakdown}\nExecutive Summary:\n{cand.summary or 'No assessment generated.'}\n{extra}"
        messagebox.showinfo(title, details)

    def open_resume(self, filename):
        resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
        filepath = os.path.join(resumes_dir, filename)
        if os.path.exists(filepath):
            try:
                os.startfile(filepath)
                self.update_status(f"Opening resume: {filename}", "#2b6b3b")
            except Exception as e:
                self.update_status(f"Error opening: {e}", "#a83232")
        else:
            self.update_status("Error: File not found.", "#a83232")
            self.refresh_resume_list()

    def delete_resume(self, filename):
        resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
        filepath = os.path.join(resumes_dir, filename)
        
        base_name, _ = os.path.splitext(filename)
        txt_filepath = os.path.join(resumes_dir, base_name + ".txt")

        deleted_pdf = False
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                deleted_pdf = True
            except Exception as e:
                self.update_status(f"Error deleting PDF: {e}", "#a83232")

        if os.path.exists(txt_filepath):
            try:
                os.remove(txt_filepath)
            except Exception:
                pass

        if deleted_pdf:
            self.update_status(f"Deleted resume: {filename}", "#2b6b3b")
        else:
            self.update_status("File not found or already deleted.", "#888888")
            
        self.refresh_resume_list()

    def delete_candidate_by_id(self, candidate_id):
        # Call API endpoint delete_candidate logic locally
        db = SessionLocal()
        try:
            from server import delete_candidate
            res = delete_candidate(candidate_id, db)
            self.update_status(res.get("message", "Candidate deleted."), "#2b6b3b")
        except Exception as e:
            self.update_status(f"Error deleting candidate: {e}", "#a83232")
        finally:
            db.close()
            self.refresh_resume_list()

    # ── Resumes Directory Management ──
    def refresh_resume_list(self):
        # Clear existing items in scrollable frame
        for widget in self.resumes_scroll.winfo_children():
            widget.destroy()

        resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
        if not os.path.exists(resumes_dir):
            # Create if missing
            try:
                os.makedirs(resumes_dir)
            except Exception:
                return

        # List all PDF files
        files = [f for f in os.listdir(resumes_dir) if f.lower().endswith(".pdf")]
        
        if not files:
            empty_lbl = ctk.CTkLabel(self.resumes_scroll, text="No resumes found.", text_color="#888888")
            empty_lbl.grid(row=0, column=0, padx=10, pady=10, sticky="w")
            return

        # Auto-convert any pre-existing PDF files that lack matching .txt files
        for filename in files:
            pdf_path = os.path.join(resumes_dir, filename)
            base_name, _ = os.path.splitext(filename)
            txt_path = os.path.join(resumes_dir, base_name + ".txt")
            if not os.path.exists(txt_path):
                try:
                    text_content = []
                    with pdfplumber.open(pdf_path) as pdf:
                        for page_idx, page in enumerate(pdf.pages):
                            page_text = page.extract_text()
                            if page_text:
                                text_content.append(page_text)
                            else:
                                text_content.append(f"[Page {page_idx+1}: Empty or Scanned Image]")

                    full_text = "\n\n--- PAGE BREAK ---\n\n".join(text_content).strip()
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(full_text)
                    print(f"Auto-converted pre-existing PDF to text: {base_name}.txt")
                except Exception as e:
                    print(f"Error auto-converting {filename}: {e}")

        for idx, filename in enumerate(sorted(files)):
            # Row container frame
            row_frame = ctk.CTkFrame(self.resumes_scroll, fg_color="transparent")
            row_frame.grid(row=idx, column=0, sticky="ew", pady=5, padx=2)
            row_frame.columnconfigure(0, weight=1) # Filename takes expand space

            # Truncate filename visual to fit panel
            display_name = filename
            if len(display_name) > 22:
                display_name = display_name[:19] + "..."

            lbl = ctk.CTkLabel(row_frame, text=display_name, anchor="w")
            lbl.grid(row=0, column=0, sticky="w", padx=(5, 10))

            # Bind double click on name label to open
            lbl.bind("<Double-Button-1>", lambda e, fn=filename: self.open_resume(fn))

            # Action Buttons
            open_btn = ctk.CTkButton(
                row_frame, 
                text="Open", 
                width=50, 
                height=24,
                command=lambda fn=filename: self.open_resume(fn),
                fg_color="#2b6b3b",
                hover_color="#368c4c"
            )
            open_btn.grid(row=0, column=1, padx=2)

            del_btn = ctk.CTkButton(
                row_frame, 
                text="Del", 
                width=45, 
                height=24,
                command=lambda fn=filename: self.delete_resume(fn),
                fg_color="#a83232",
                hover_color="#c93e3e"
            )
            del_btn.grid(row=0, column=2, padx=2)

    def open_resume(self, filename):
        resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
        filepath = os.path.join(resumes_dir, filename)
        if os.path.exists(filepath):
            try:
                os.startfile(filepath)
                self.update_status(f"Opening resume: {filename}", "#2b6b3b")
            except Exception as e:
                self.update_status(f"Error opening: {e}", "#a83232")
        else:
            self.update_status("Error: File not found.", "#a83232")
            self.refresh_resume_list()

    def delete_resume(self, filename):
        resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")
        filepath = os.path.join(resumes_dir, filename)
        
        # Determine the matching .txt file path
        base_name, _ = os.path.splitext(filename)
        txt_filepath = os.path.join(resumes_dir, base_name + ".txt")

        # Delete PDF file
        deleted_pdf = False
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                deleted_pdf = True
            except Exception as e:
                self.update_status(f"Error deleting PDF: {e}", "#a83232")

        # Delete matching TXT file if it exists
        deleted_txt = False
        if os.path.exists(txt_filepath):
            try:
                os.remove(txt_filepath)
                deleted_txt = True
            except Exception:
                pass

        if deleted_pdf:
            msg = f"Deleted resume: {filename}"
            if deleted_txt:
                msg += " (and text file)"
            self.update_status(msg, "#2b6b3b")
        else:
            self.update_status("File not found or already deleted.", "#888888")
            
        self.refresh_resume_list()

# ── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = LinkedInBotApp()
    app.mainloop()
