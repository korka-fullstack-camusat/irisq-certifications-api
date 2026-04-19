from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class CandidateAccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    first_name: str
    last_name: str
    phone: Optional[str] = None
    profile: Optional[str] = None
    date_of_birth: Optional[str] = None


class CandidateAccountInDB(BaseModel):
    email: EmailStr
    hashed_password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    profile: Optional[str] = None
    date_of_birth: Optional[str] = None
    account_id: str
    created_at: datetime
    must_change_password: bool = False


class CandidateAccountOut(BaseModel):
    id: str
    account_id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    profile: Optional[str] = None
    date_of_birth: Optional[str] = None
    created_at: Optional[str] = None
