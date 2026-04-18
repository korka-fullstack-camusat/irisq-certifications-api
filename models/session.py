from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SessionBase(BaseModel):
    name: str  # e.g. "Session Avril 2026"
    description: Optional[str] = None
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None    # YYYY-MM-DD
    status: str = "active"            # active | closed


class SessionCreate(SessionBase):
    pass


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None


class SessionDBModel(SessionBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
    sequence_number: Optional[int] = None
    candidate_counter: Optional[int] = 0

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
