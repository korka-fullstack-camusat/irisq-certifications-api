from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class FormField(BaseModel):
    id: str
    type: str # text, email, select, etc.
    label: str
    required: bool = False
    options: Optional[List[str]] = None

class FormBase(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = "Général"
    status: str = "draft" # draft, active, closed
    fields: List[FormField] = []

class FormCreate(FormBase):
    pass

class FormResponseModel(FormBase):
    id: str = Field(alias="_id")
    responses_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
