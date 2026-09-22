from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FormationCreate(BaseModel):
    title: str
    description: Optional[str] = None
    is_active: bool = True


class FormationUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class FormationOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
