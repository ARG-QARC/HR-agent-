import os
from unittest.mock import patch
from src.domain.scoring import score_resume_against_job
from src.infrastructure.ai.gemini_client import get_models

def test_gemini_models_list():
    models = get_models()
    assert isinstance(models, list)
    assert "gemini-2.5-flash" in models
    assert "gemini-2.0-flash" in models

def test_score_handles_missing_api_key():
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        with patch("src.domain.scoring.get_client", return_value=None):
            result = score_resume_against_job("Python Developer", "Python skills required", "Senior Python Dev", "")
            assert result["relevance_score"] == 0
            assert "GEMINI_API_KEY not configured" in result["match_summary"]
