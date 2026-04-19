from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class CandidateAccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    first_name: str
    last_name: str
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    profile: Optional[str] = None  # "Salarié", "Indépendant", "Demandeur d'emploi", etc.
    company: Optional[str] = None
    nationality: Optional[str] = None


class CandidateAccountUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    profile: Optional[str] = None
    company: Optional[str] = None
    nationality: Optional[str] = None


class CandidateAccountLoginIn(BaseModel):
    email: EmailStr
    password: str


class CandidateAccountLoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account_id: str


class CandidateAccountForgotPasswordIn(BaseModel):
    email: EmailStr


class CandidateAccountChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class CandidateApplyIn(BaseModel):
    form_id: str
    session_id: Optional[str] = None
    exam_mode: str  # "online" | "onsite"
    exam_type: Optional[str] = None  # "direct" | "after_formation"
    answers: Optional[dict] = None  # documents uploadés + champs additionnels
