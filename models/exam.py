from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ExamBase(BaseModel):
    certification: str
    title: str
    document_url: str
    duration_minutes: Optional[int] = None
    session_id: Optional[str] = None
    start_time: Optional[str] = None          # ISO 8601 datetime string

class ExamCreate(ExamBase):
    pass

class ExamDBModel(ExamBase):
    id: str = Field(alias="_id")
    created_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
