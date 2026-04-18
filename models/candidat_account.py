from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class CandidatAccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    nom: str
    prenom: str
    telephone: str
    date_naissance: Optional[str] = None
    lieu_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    adresse: Optional[str] = None


class CandidatAccountUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    date_naissance: Optional[str] = None
    lieu_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    adresse: Optional[str] = None
