from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class CandidateAccountCreate(BaseModel):
    # Identité & contact (image Étape 1)
    last_name: str
    first_name: str
    date_of_birth: str           # obligatoire
    birth_place: Optional[str] = None
    nationality: Optional[str] = None
    phone: str                   # obligatoire
    email: EmailStr              # obligatoire
    years_experience: str        # obligatoire (ex: "3")
    address: Optional[str] = None
    # Accès
    password: str = Field(min_length=6, max_length=128)


class CandidateAccountUpdate(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    birth_place: Optional[str] = None
    nationality: Optional[str] = None
    phone: Optional[str] = None
    years_experience: Optional[str] = None
    address: Optional[str] = None


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
    exam_mode: str               # "online" | "onsite"
    exam_type: Optional[str] = None  # "direct" | "after_formation"
    answers: Optional[dict] = None   # documents uploadés
