import os
import sys
import time
import subprocess
from google import genai
from dotenv import load_dotenv

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
    """
    Sends the raw post draft to Gemini and returns a refined,
    professional LinkedIn post. Falls back to the raw text if
    the API key is missing or all call attempts fail.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here" or not GEMINI_API_KEY.strip():
        print("[Gemini] No API key set — posting raw text as-is.")
        return raw_text

    print(f"[Gemini] Refining post draft (using key starting with: {GEMINI_API_KEY[:6]})...")
    
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

    # Try different models in case of server overload (503) or rate limits (429)
    models_to_try = [
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-latest"
    ]

    for model_name in models_to_try:
        # Try up to 3 times per model
        for attempt in range(3):
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                refined = response.text.strip()
                print(f"[Gemini] Refinement complete using model: {model_name}!")
                print("\n" + "-" * 60)
                print("REFINED POST PREVIEW:")
                print("-" * 60)
                print(refined)
                print("-" * 60 + "\n")
                return refined
            except Exception as e:
                print(f"[Gemini] Attempt {attempt+1}/3 failed with model '{model_name}': {e}")
                time.sleep(2)

    print("[Gemini] All models and retry attempts failed. Falling back to raw text.")
    return raw_text

def apply_feedback_with_gemini(current_text: str, feedback: str) -> str:
    """
    Applies user feedback to the current refined post using Gemini.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here" or not GEMINI_API_KEY.strip():
        print("[Gemini] No API key set — cannot apply feedback.")
        return current_text

    print(f"[Gemini] Applying feedback: '{feedback}'...")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        # Build context memory block
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
        updated = response.text.strip()
        print("[Gemini] Content updated successfully!")
        return updated
    except Exception as e:
        print(f"[Gemini] Error applying feedback: {e}")
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

def run_bot(post_text: str):
    print("============================================================")
    print("LINKEDIN AUTOMATION BOT STARTING...")
    print("============================================================")

    # Step 1: Initial refinement
    refined_text = refine_with_gemini(post_text)

    # Step 2: Interactive Chat/Refinement Loop
    while True:
        print("\n" + "=" * 70)
        print("LINKEDIN POST CONTENT VERIFICATION & REFINEMENT")
        print("=" * 70)
        print(f"\nRefined Post Text:\n\n{refined_text}\n")
        print("How would you like to proceed?")
        print("  - Press ENTER or type 'y' to APPROVE and publish.")
        print("  - Type 'n' to REJECT and cancel.")
        print("  - Or type any feedback to modify (e.g., 'change experience to 5 years', 'make it an internship')")
        print("=" * 70 + "\n")

        user_choice = input("Your input: ").strip()
        
        # Check approval
        if user_choice.lower() in ["y", "yes", ""]:
            break
        # Check cancellation
        elif user_choice.lower() == "n":
            print("\nPost rejected. Cancelled.")
            return
        # If anything else, treat it as refinement feedback!
        else:
            refined_text = apply_feedback_with_gemini(refined_text, user_choice)

    print("\nApproved! Processing content to publish...")

    # Step 3: Copy refined post to system clipboard
    import pyperclip
    try:
        pyperclip.copy(refined_text)
        print("\n[Clipboard] Polished post content successfully copied to your clipboard!")
    except Exception as e:
        print(f"\n[Clipboard] Warning: Could not copy to clipboard: {e}")

    # Step 4: Launch LinkedIn Windows App
    print("\nLaunching LinkedIn Windows Desktop App...")
    app_id = "7EE7776C.LinkedInforWindows_w1wdnht996qgy!App"
    try:
        # Launch UWP app via explorer.exe shell protocol
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("LinkedIn app command sent successfully.")
    except Exception as e:
        print(f"Error launching LinkedIn app: {e}")

    # Step 5: Focus the LinkedIn Window
    print("Waiting for LinkedIn window to appear...")
    time.sleep(5)
    
    from pywinauto import Desktop
    desktop = Desktop(backend="uia")
    app_win = get_linkedin_app_window(desktop)
    focused_success = False

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

    # Step 6: Locate and Click the "Start a post" control inside the app
    clicked_start_post = False
    if focused_success and app_win:
        print("Searching for 'Start a post' button inside the LinkedIn app...")
        try:
            # Find the button matching "Start a post"
            # UIA exposes web content inside PWAs as native controls
            start_btn = app_win.child_window(title="Start a post", control_type="Button")
            if start_btn.exists():
                start_btn.click_input()
                print("Clicked 'Start a post' button automatically!")
                clicked_start_post = True
            else:
                # Fallback: check child controls with title matching start a post
                start_btn_loose = app_win.child_window(title_re=".*Start a post.*", control_type="Button")
                if start_btn_loose.exists():
                    start_btn_loose.click_input()
                    print("Clicked 'Start a post' button (loose match) automatically!")
                    clicked_start_post = True
        except Exception as e:
            print(f"Note: Could not click button automatically: {e}")

    # If automatic click failed, ask user to click it
    if not clicked_start_post:
        print("\nPlease click the 'Start a post' box manually in the LinkedIn window now.")
        print("Waiting 6 seconds for you to do so...")
        time.sleep(6)
    else:
        # Wait for the editor dialog to fully render
        time.sleep(2)

    # Step 7: Automatically paste the text using keyboard
    import keyboard
    print("Pasting post content into the editor...")
    try:
        # Send Ctrl+V to paste the clipboard text into the active cursor
        keyboard.send("ctrl+v")
        print("Content pasted!")
    except Exception as e:
        print(f"Error pasting content: {e}")

    # Step 8: Specific Terminal Notice
    print("\n" + "=" * 70)
    print("NOTICE: Open LinkedIn that is already there in the background and post the things after I stop working.")
    print("=" * 70 + "\n")

    # Step 9: Trigger the separate publishing bot (launch external script)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        publish_bot_path = os.path.join(script_dir, "post_playwright.py")
        subprocess.run([sys.executable, publish_bot_path])
    except Exception as e:
        print(f"Error launching publishing bot: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python linkedin_bot.py "Your post text here"')
        sys.exit(1)

    text = sys.argv[1]
    run_bot(text)


