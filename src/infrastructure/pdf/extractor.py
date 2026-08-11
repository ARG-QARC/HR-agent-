import os
import pdfplumber
from src.infrastructure.ai.gemini_client import get_client, VERIFIED_GEMINI_MODELS

def extract_scanned_pdf_with_gemini(pdf_path: str) -> str:
    """Uses Gemini Vision API to OCR image-based or scanned PDF files."""
    client = get_client()
    if not client:
        return ""

    try:
        pdf_file = client.files.upload(file=pdf_path)
        prompt = "Extract all raw text from this resume PDF document clearly. Maintain formatting and structure."
        
        for model in VERIFIED_GEMINI_MODELS:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[pdf_file, prompt]
                )
                if response and hasattr(response, "text") and response.text:
                    return response.text.strip()
            except Exception:
                continue
    except Exception as e:
        print(f"[PDFExtractor] Gemini OCR notice for {pdf_path}: {e}")

    return ""

def extract_pdf_text(pdf_path: str) -> str:
    """
    Centralized PDF extraction service.
    First attempts native text extraction via pdfplumber, falling back to Gemini Vision OCR if necessary.
    """
    if not os.path.exists(pdf_path):
        return ""

    extracted_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            extracted_text = "\n".join(pages_text).strip()
    except Exception as e:
        print(f"[PDFExtractor] pdfplumber error on {pdf_path}: {e}")

    # Fallback to Gemini OCR if text is less than 50 characters (scanned/image PDF)
    if len(extracted_text) < 50:
        ocr_text = extract_scanned_pdf_with_gemini(pdf_path)
        if ocr_text:
            extracted_text = ocr_text

    return extracted_text
