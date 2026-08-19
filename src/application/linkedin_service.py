"""
linkedin_service.py — LinkedIn Desktop Automation Service
==========================================================
Provides a reusable function to automate opening the LinkedIn desktop/UWP app,
navigating to the "Start a post" editor, and pasting pre-generated job post
content into the editor text area.

IMPORTANT: This service intentionally does NOT click the final "Post" button.
The user retains full manual control over the publish action, allowing them
to review formatting, add hashtags, attach media, or cancel before posting.

Dependencies:
    - pywinauto  : Windows UI automation (UIA backend) for finding/clicking controls
    - pyperclip  : Cross-platform clipboard access for copying post text
    - keyboard   : Low-level keyboard simulation for Ctrl+V paste

Usage:
    from src.application.linkedin_service import linkedin_auto_post
    result = linkedin_auto_post("Your job post text here", "Senior Data Scientist")
    # result = {"status": "success"|"partial"|"error", "message": "..."}
"""

import os
import sys
import time
import subprocess

# Force stdout/stderr to UTF-8 encoding on Windows to prevent Unicode crashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ── LinkedIn UWP App Identifier ──────────────────────────────────────────────
# This is the Windows Store / UWP app ID for the official LinkedIn Windows app.
# Used to launch the app via `explorer.exe shell:AppsFolder\<app_id>`.
LINKEDIN_UWP_APP_ID = "7EE7776C.LinkedInforWindows_w1wdnht996qgy!App"

# ── LinkedIn Web Fallback URL ────────────────────────────────────────────────
LINKEDIN_WEB_URL = "https://www.linkedin.com/"


def _get_linkedin_app_window(desktop):
    """
    Locate the native LinkedIn UWP/PWA app window using pywinauto's UIA backend.

    Search strategy (ordered by specificity):
      1. Exact title "LinkedIn" with UWP class "ApplicationFrameWindow"
      2. Exact title "LinkedIn" (any window class)
      3. Title containing "LinkedIn" but NOT a browser window (Chrome, Firefox, Explorer)

    Args:
        desktop: A pywinauto.Desktop instance with backend="uia".

    Returns:
        The matched window wrapper, or None if no LinkedIn window is found.
    """
    # ── Pass 1: Exact UWP match (most reliable) ──────────────────────────────
    for win in desktop.windows():
        try:
            title = win.window_text()
            cls = win.class_name()
            if title == "LinkedIn" and cls == "ApplicationFrameWindow":
                return desktop.window(handle=win.handle)
        except Exception:
            continue

    # ── Pass 2: Exact title match (any class) ────────────────────────────────
    for win in desktop.windows():
        try:
            if win.window_text() == "LinkedIn":
                return desktop.window(handle=win.handle)
        except Exception:
            continue

    # ── Pass 3: Fuzzy match excluding known browser classes ──────────────────
    browser_classes = {"Chrome_WidgetWin_1", "MozillaWindowClass", "CabinetWClass"}
    for win in desktop.windows():
        try:
            title = win.window_text()
            cls = win.class_name()
            if "LinkedIn" in title and cls not in browser_classes:
                return desktop.window(handle=win.handle)
        except Exception:
            continue

    return None


def _launch_linkedin_app():
    """
    Attempt to launch the LinkedIn Windows UWP app.

    Falls back to opening LinkedIn in the default web browser if the UWP
    app launch command fails (e.g., app not installed).

    Returns:
        str: "uwp" if UWP app was launched, "browser" if browser fallback was used.
    """
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{LINKEDIN_UWP_APP_ID}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("[LinkedIn Service] UWP app launch command sent.")
        return "uwp"
    except Exception as e:
        print(f"[LinkedIn Service] UWP launch failed ({e}), falling back to browser.")
        try:
            os.startfile(LINKEDIN_WEB_URL)
        except Exception:
            subprocess.Popen(["explorer.exe", LINKEDIN_WEB_URL])
        return "browser"


def _focus_window(app_win):
    """
    Bring the LinkedIn window to the foreground and restore it if minimized.

    Args:
        app_win: A pywinauto window wrapper.

    Returns:
        bool: True if the window was successfully focused, False otherwise.
    """
    try:
        if app_win.is_minimized():
            app_win.restore()
        app_win.set_focus()
        print("[LinkedIn Service] Window focused successfully.")
        return True
    except Exception as e:
        print(f"[LinkedIn Service] Failed to focus window: {e}")
        return False


def _click_start_post_button(app_win):
    """
    Attempt to find and click the "Start a post" button inside the LinkedIn app.

    Tries two matching strategies:
      1. Exact title match: control_type="Button", title="Start a post"
      2. Loose regex match: title_re=".*Start a post.*"

    Args:
        app_win: A focused pywinauto window wrapper for the LinkedIn app.

    Returns:
        bool: True if the button was found and clicked, False otherwise.
    """
    print("[LinkedIn Service] Searching for 'Start a post' button...")
    try:
        # ── Strategy 1: Exact title match ────────────────────────────────────
        start_btn = app_win.child_window(title="Start a post", control_type="Button")
        if start_btn.exists(timeout=3):
            start_btn.click_input()
            print("[LinkedIn Service] Clicked 'Start a post' button (exact match).")
            return True
    except Exception:
        pass

    try:
        # ── Strategy 2: Loose regex match ────────────────────────────────────
        start_btn_loose = app_win.child_window(
            title_re=".*[Ss]tart a post.*", control_type="Button"
        )
        if start_btn_loose.exists(timeout=3):
            start_btn_loose.click_input()
            print("[LinkedIn Service] Clicked 'Start a post' button (regex match).")
            return True
    except Exception:
        pass

    try:
        # ── Strategy 3: Look for any clickable element mentioning "post" ─────
        start_btn_text = app_win.child_window(title_re=".*[Ss]tart.*post.*")
        if start_btn_text.exists(timeout=2):
            start_btn_text.click_input()
            print("[LinkedIn Service] Clicked 'Start a post' element (text match).")
            return True
    except Exception:
        pass

    print("[LinkedIn Service] Could not find 'Start a post' button automatically.")
    return False


def linkedin_auto_post(post_text: str, job_title: str = "Job Position") -> dict:
    """
    Main automation function: opens LinkedIn, pastes post content into the editor.

    This function performs the following steps:
      1. Copy the post text to the system clipboard
      2. Launch the LinkedIn desktop app (UWP) or browser fallback
      3. Wait for the LinkedIn window to appear (up to 12 seconds)
      4. Focus the window and bring it to the foreground
      5. Find and click the "Start a post" button
      6. Wait for the post editor to render
      7. Paste the clipboard content into the editor (Ctrl+V)

    The function intentionally does NOT click the final "Post" button.
    The user must review and manually click "Post" on LinkedIn.

    Args:
        post_text (str): The full job post text to paste into LinkedIn.
        job_title (str): The job title for logging/context purposes.

    Returns:
        dict: A result dictionary with keys:
            - "status": "success" | "partial" | "error"
            - "message": Human-readable description of what happened.
            - "launch_method": "uwp" | "browser" (how LinkedIn was opened)
    """
    print("=" * 65)
    print(f"[LinkedIn Service] Auto-posting for: {job_title}")
    print("=" * 65)

    # ── Step 1: Copy post text to system clipboard ───────────────────────────
    try:
        import pyperclip
        pyperclip.copy(post_text)
        print("[LinkedIn Service] Post content copied to clipboard.")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to copy post to clipboard: {e}",
            "launch_method": "none"
        }

    # ── Step 2: Launch LinkedIn app ──────────────────────────────────────────
    launch_method = _launch_linkedin_app()

    # ── Step 3: Wait for LinkedIn window to appear ───────────────────────────
    print("[LinkedIn Service] Waiting for LinkedIn window to appear...")
    time.sleep(5)  # Initial wait for app to launch

    try:
        from pywinauto import Desktop
    except ImportError:
        return {
            "status": "partial",
            "message": "LinkedIn app launched and post copied to clipboard, but pywinauto is not installed for window automation. Please click 'Start a post' and press Ctrl+V to paste.",
            "launch_method": launch_method
        }

    desktop = Desktop(backend="uia")
    app_win = None

    # Poll for up to 12 seconds (beyond the initial 5-second wait)
    for attempt in range(12):
        app_win = _get_linkedin_app_window(desktop)
        if app_win:
            break
        time.sleep(1)

    if not app_win:
        return {
            "status": "partial",
            "message": "LinkedIn app launched and post copied to clipboard, but the window could not be detected. Please click 'Start a post' manually and press Ctrl+V to paste.",
            "launch_method": launch_method
        }

    # ── Step 4: Focus the LinkedIn window ────────────────────────────────────
    focused = _focus_window(app_win)
    if not focused:
        return {
            "status": "partial",
            "message": "LinkedIn app is open and post is in clipboard. Could not auto-focus the window. Please click 'Start a post' and press Ctrl+V.",
            "launch_method": launch_method
        }

    # ── Step 5: Click "Start a post" button ──────────────────────────────────
    clicked = _click_start_post_button(app_win)

    if not clicked:
        return {
            "status": "partial",
            "message": "LinkedIn app is focused and post is in clipboard. Could not find the 'Start a post' button automatically. Please click it manually, then press Ctrl+V to paste your post.",
            "launch_method": launch_method
        }

    # ── Step 6: Wait for post editor to render ───────────────────────────────
    time.sleep(2.5)

    # ── Step 7: Paste content into the editor via Ctrl+V ─────────────────────
    try:
        import keyboard
        keyboard.send("ctrl+v")
        print("[LinkedIn Service] Content pasted into editor via Ctrl+V.")
    except ImportError:
        return {
            "status": "partial",
            "message": "LinkedIn post editor is open and post is in clipboard. The 'keyboard' package is not installed for auto-paste. Please press Ctrl+V manually to paste.",
            "launch_method": launch_method
        }
    except Exception as e:
        return {
            "status": "partial",
            "message": f"LinkedIn post editor is open. Auto-paste failed ({e}). Please press Ctrl+V manually to paste your post.",
            "launch_method": launch_method
        }

    print("[LinkedIn Service] ✅ Post content successfully pasted into LinkedIn editor.")
    print("[LinkedIn Service] Awaiting user to review and click 'Post' on LinkedIn.")

    return {
        "status": "success",
        "message": "Post content has been pasted into the LinkedIn editor. Review your post and click the 'Post' button on LinkedIn when ready.",
        "launch_method": launch_method
    }
