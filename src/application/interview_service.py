import asyncio
from typing import Dict, Any, Tuple
from src.infrastructure.email.smtp_sender import send_interview_invitation_email

class InterviewService:
    @staticmethod
    async def send_interview_invitation_async(payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Dispatches SMTP interview invitation email asynchronously using asyncio.to_thread()."""
        return await asyncio.to_thread(send_interview_invitation_email, payload)
