from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from bson import ObjectId

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str # "RH", "EVALUATEUR", "CORRECTEUR"
    full_name: Optional[str] = None

class UserInDB(BaseModel):
    email: EmailStr
    hashed_password: str
    role: str
    full_name: Optional[str] = None
    created_at: datetime

class UserOut(BaseModel):
    id: str
    email: str
    role: str
    full_name: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
