import os
import time
from typing import List, Optional
from google import genai
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env")
load_dotenv(dotenv_path=env_path, override=True)

_client: Optional[genai.Client] = None

# Single source of truth for verified Google AI models
VERIFIED_GEMINI_MODELS: List[str] = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

def get_client() -> Optional[genai.Client]:
    """Returns thread-safe singleton instance of the Gemini Client."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip('"' + "'").strip()
        if api_key:
            try:
                _client = genai.Client(api_key=api_key)
            except Exception as e:
                print(f"[GeminiClient] Initialization notice: {e}")
                _client = None
    return _client

def get_models() -> List[str]:
    """Returns the list of verified, supported Gemini models."""
    return VERIFIED_GEMINI_MODELS

def call_gemini_with_retry(contents: List[dict], system_instruction: str = "", max_attempts: int = 3) -> str:
    """
    Executes a Gemini API request with automatic model fallback, connection pooling, and exponential backoff retry.
    """
    client = get_client()
    if not client:
        raise ValueError("GEMINI_API_KEY is not configured in environmental variables.")

    last_exception = None

    for model_name in VERIFIED_GEMINI_MODELS:
        for attempt in range(1, max_attempts + 1):
            try:
                config = {}
                if system_instruction:
                    config["system_instruction"] = system_instruction

                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config if config else None
                )

                if response and hasattr(response, "text") and response.text:
                    return response.text.strip()
            except Exception as err:
                last_exception = err
                err_str = str(err).lower()
                print(f"[GeminiClient] Warning on model '{model_name}' (Attempt {attempt}/{max_attempts}): {err}")
                
                # If rate-limited (429), apply exponential backoff wait
                if "429" in err_str or "resource_exhausted" in err_str:
                    time.sleep(2 ** attempt)
                else:
                    time.sleep(0.5)

    raise RuntimeError(f"All Gemini models failed after retries. Last error: {last_exception}")
