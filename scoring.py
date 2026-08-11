import os
import sys
import time
import json
from google import genai
from dotenv import load_dotenv

# Load environmental variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path, override=True)

# Initialize Gemini Client
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip('"' + "'").strip()
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Fallback chain of models to try
GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.0-flash",
]

class ScoringResult(dict):
    """
    Dictionary subclass that supports tuple unpacking (score, summary)
    for backward compatibility with existing codebase callers.
    """
    def __iter__(self):
        yield self.get("score", 0)
        yield self.get("match_summary", self.get("summary", "No evaluation generated."))


def score_resume_against_job(
    job_title: str,
    job_description: str,
    resume_text: str,
    email_body: str = ""
) -> ScoringResult:
    """
    Evaluates a candidate's resume and email body against a job description using Gemini AI.
    
    Multi-dimensional scoring categories:
      - Skills Match: 0 to 35 points
      - Experience Match: 0 to 35 points
      - Education: 0 to 15 points
      - Location & Relevance: 0 to 15 points
      - Total Score: Sum of categories (0 to 100)

    Returns a ScoringResult dictionary containing:
      score, skills_score, experience_score, education_score, location_score,
      recommendation (HIRE, INTERVIEW, REJECT), match_summary, strengths, gaps.
    Supports tuple unpacking: score, summary = score_resume_against_job(...)
    """
    default_result = ScoringResult({
        "score": 0,
        "skills_score": 0,
        "experience_score": 0,
        "education_score": 0,
        "location_score": 0,
        "recommendation": "REJECT",
        "match_summary": "Error: Evaluation incomplete.",
        "strengths": [],
        "gaps": []
    })

    if not client:
        default_result["match_summary"] = "Error: Gemini API Key not configured."
        return default_result

    combined_candidate_info = ""
    if email_body and email_body.strip():
        combined_candidate_info += f"--- APPLICATION EMAIL BODY ---\n{email_body.strip()}\n\n"
    combined_candidate_info += f"--- EXTRACTED RESUME TEXT ---\n{resume_text.strip() if resume_text else '[No Resume Text]'}"

    if not combined_candidate_info.strip():
        default_result["match_summary"] = "Error: Candidate submission contains no readable text."
        return default_result

    prompt = f"""You are an expert technical recruiter analyzing a candidate's application (resume + email) for a job opening.

Job Title: {job_title}

Job Description:
{job_description}

Candidate Application & Resume Data:
{combined_candidate_info}

Perform a rigorous multi-dimensional evaluation of the candidate across these 4 specific dimensions:
1. Skills Match (0 to 35 points): How well do technical & domain skills match requirement lists?
2. Experience Match (0 to 35 points): How relevant are past job roles, responsibilities, and project impact?
3. Education (0 to 15 points): Degree field, level, certifications, or academic background.
4. Location & Relevance (0 to 15 points): Location compatibility, application quality, enthusiasm, and overall fit.

Calculate the Total Score as the exact sum of these 4 sub-scores (0 to 100).
Assign a Recommendation: "HIRE" (total score >= 80), "INTERVIEW" (total score 55-79), or "REJECT" (total score < 55).

Return your evaluation as a STRICT JSON object with NO extra text or markdown formatting outside JSON. Use this exact schema:
{{
  "skills_score": <number 0-35>,
  "experience_score": <number 0-35>,
  "education_score": <number 0-15>,
  "location_score": <number 0-15>,
  "score": <number 0-100>,
  "recommendation": "HIRE" | "INTERVIEW" | "REJECT",
  "match_summary": "<2 to 3 sentence executive summary of overall candidate fit>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "gaps": ["<gap/missing requirement 1>", "<gap/missing requirement 2>"]
}}"""

    for model_name in GEMINI_MODELS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                text_out = response.text.strip()
                
                # Strip markdown code blocks if present
                if text_out.startswith("```"):
                    lines = text_out.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text_out = "\n".join(lines).strip()

                parsed_json = json.loads(text_out)

                skills_sc = int(parsed_json.get("skills_score", 0))
                exp_sc = int(parsed_json.get("experience_score", 0))
                edu_sc = int(parsed_json.get("education_score", 0))
                loc_sc = int(parsed_json.get("location_score", 0))

                total_sc = parsed_json.get("score")
                if total_sc is None:
                    total_sc = skills_sc + exp_sc + edu_sc + loc_sc
                else:
                    total_sc = int(total_sc)

                rec = str(parsed_json.get("recommendation", "")).upper()
                if rec not in ["HIRE", "INTERVIEW", "REJECT"]:
                    if total_sc >= 80:
                        rec = "HIRE"
                    elif total_sc >= 55:
                        rec = "INTERVIEW"
                    else:
                        rec = "REJECT"

                summary_text = parsed_json.get("match_summary") or parsed_json.get("summary") or "Evaluation complete."
                strengths_list = parsed_json.get("strengths", [])
                if isinstance(strengths_list, str):
                    strengths_list = [strengths_list]
                gaps_list = parsed_json.get("gaps", [])
                if isinstance(gaps_list, str):
                    gaps_list = [gaps_list]

                res = ScoringResult({
                    "score": max(0, min(100, total_sc)),
                    "skills_score": max(0, min(35, skills_sc)),
                    "experience_score": max(0, min(35, exp_sc)),
                    "education_score": max(0, min(15, edu_sc)),
                    "location_score": max(0, min(15, loc_sc)),
                    "recommendation": rec,
                    "match_summary": summary_text,
                    "strengths": strengths_list,
                    "gaps": gaps_list
                })
                print(f"[Scoring] Evaluated resume with Gemini ({model_name}): Score {res['score']}/100 [{res['recommendation']}]")
                return res

            except Exception as e:
                print(f"[Scoring] Model {model_name} attempt {attempt+1} failed: {e}")
                time.sleep(1.5)

    default_result["match_summary"] = "Evaluation timed out or failed across all Gemini models."
    return default_result
