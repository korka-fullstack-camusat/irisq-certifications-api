from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class CandidateRegisterIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    prenom: str = Field(min_length=1, max_length=120)
    date_naissance: str = Field(min_length=1, max_length=40)
    lieu_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    telephone: str = Field(min_length=3, max_length=40)
    email: EmailStr
    annees_experience: str = Field(min_length=1, max_length=10)
    adresse: Optional[str] = None
    password: str = Field(min_length=6, max_length=128)
    password_confirm: str = Field(min_length=6, max_length=128)


class CandidateLoginIn(BaseModel):
    email: EmailStr
    password: str


class CandidateLoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account_id: str


class CandidateAccountOut(BaseModel):
    id: str
    nom: str
    prenom: str
    email: EmailStr
    telephone: str
    date_naissance: str
    lieu_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    adresse: Optional[str] = None
    annees_experience: str
    created_at: datetime


class CandidateApplyIn(BaseModel):
    form_id: Optional[str] = None
    session_id: Optional[str] = None
    certification: str
    exam_mode: str  # "online" | "onsite"
    exam_type: str  # "direct" | "after_formation"
    cv_url: Optional[str] = None
    piece_identite_url: Optional[str] = None
    justificatif_experience_url: Optional[str] = None
    diplomes_url: Optional[str] = None
    attestation_formation_url: Optional[str] = None
    amenagement: Optional[str] = None
    amenagement_details: Optional[str] = None
    declaration_accepted: bool = False
