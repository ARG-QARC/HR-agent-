import datetime
from dataclasses import dataclass
from typing import Optional

@dataclass
class JobEntity:
    job_id: str
    title: str
    description: str
    subject_tag: str
    created_at: Optional[datetime.datetime] = None

    def validate(self) -> bool:
        if not self.job_id or not self.title or not self.description:
            raise ValueError("Job Entity requires job_id, title, and description.")
        return True
