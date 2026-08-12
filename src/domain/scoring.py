import json
from typing import Dict, Any
from src.infrastructure.ai.gemini_client import call_gemini_with_retry, get_client

def score_resume_against_job(job_title: str, job_description: str, resume_text: str, email_body: str = "") -> Dict[str, Any]:
    """
    Single source of truth for candidate resume scoring against job specifications.
    Returns structured scores, recommendation, strengths, gaps, and match summary.
    """
    default_result = {
        "relevance_score": 0,
        "skills_score": 0,
        "experience_score": 0,
        "education_score": 0,
        "location_score": 0,
        "recommendation": "REJECT",
        "strengths": [],
        "gaps": ["Evaluation pending or failed."],
        "match_summary": "Evaluation incomplete.",
        "status": "Failed"
    }

    if not get_client():
        default_result["match_summary"] = "Error: GEMINI_API_KEY not configured."
        return default_result

    prompt = f"""Evaluate candidate resume against job description:

JOB POSITION: {job_title}
JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME TEXT:
{resume_text[:4000]}

CANDIDATE EMAIL COVER LETTER:
{email_body[:1000]}

Task: Perform multi-dimensional evaluation. Return ONLY a valid JSON object matching this schema:
{{
  "relevance_score": 85,
  "skills_score": 80,
  "experience_score": 85,
  "education_score": 90,
  "location_score": 80,
  "recommendation": "HIRE",
  "strengths": ["Strong Python expertise", "Relevant domain background"],
  "gaps": ["Requires relocation"],
  "match_summary": "Excellent fit with strong technical experience."
}}"""

    system_prompt = (
        "SYSTEM ARCHITECTURE & IDENTITY OVERVIEW:\n"
        "You are RecruiterAI, an expert AI Candidate Scoring Evaluator operating within the 'RecruiterAI Automated Agent' system.\n\n"
        "YOUR CORE EVALUATION RESPONSIBILITIES:\n"
        "1. Perform unbiased multi-dimensional evaluation of applicant resumes against target job descriptions.\n"
        "2. Score candidate across 5 core dimensions: Relevance (0-100), Technical Skills, Relevant Experience, Education, and Location.\n"
        "3. Provide strict, realistic recommendations: STRONG HIRE, HIRE, CONSIDER, or REJECT.\n"
        "4. Extract key candidate strengths and skill gaps as bullet points.\n"
        "5. Output ONLY valid JSON matching the requested schema."
    )

    try:
        response_text = call_gemini_with_retry(
            contents=[{"parts": [{"text": prompt}]}],
            system_instruction=system_prompt
        )

        match = response_text.find('{')
        end_match = response_text.rfind('}')
        if match != -1 and end_match != -1:
            json_str = response_text[match:end_match+1]
            data = json.loads(json_str)
            
            # Normalize fields
            res = {
                "relevance_score": int(data.get("relevance_score", 0)),
                "skills_score": int(data.get("skills_score", 0)),
                "experience_score": int(data.get("experience_score", 0)),
                "education_score": int(data.get("education_score", 0)),
                "location_score": int(data.get("location_score", 0)),
                "recommendation": str(data.get("recommendation", "INTERVIEW")).upper(),
                "strengths": data.get("strengths", []) if isinstance(data.get("strengths"), list) else [str(data.get("strengths"))],
                "gaps": data.get("gaps", []) if isinstance(data.get("gaps"), list) else [str(data.get("gaps"))],
                "match_summary": str(data.get("match_summary", "Evaluation complete.")),
                "status": "Scored"
            }
            return res
    except Exception as e:
        print(f"[DomainScoring] Scoring error: {e}")
        default_result["match_summary"] = f"Error during AI evaluation: {e}"

    return default_result
