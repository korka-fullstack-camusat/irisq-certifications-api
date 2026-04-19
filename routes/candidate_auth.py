"""
Authentification dédiée aux candidats.

Flow:
- Le candidat crée un compte via POST /api/candidate/register
  (email + mot de passe + informations personnelles).
- Il se connecte via POST /api/candidate/login (email + mot de passe).
- Le token JWT contient l'ObjectId du document dans candidate_accounts.
- Il peut ensuite voir les certifications disponibles et candidater.
à une formation. Chaque candidature génère un matricule unique (public_id).
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId

from database import get_database
from models.candidate_account import CandidateAccountCreate, CandidateAccountOut
from utils.security import SECRET_KEY, ALGORITHM, verify_password, get_password_hash

router = APIRouter()

CANDIDATE_TOKEN_AUDIENCE = "candidate"
CANDIDATE_TOKEN_EXPIRE_DAYS = 14

_candidate_scheme = OAuth2PasswordBearer(tokenUrl="/api/candidate/login", auto_error=False)


class CandidateLoginIn(BaseModel):
    email: EmailStr
    password: str


class CandidateLoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account_id: str
    must_change_password: bool = False


class CandidateChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class CandidateForgotPasswordIn(BaseModel):
    email: EmailStr


class CandidateForgotPasswordOut(BaseModel):
    message: str


def create_candidate_token(account_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=CANDIDATE_TOKEN_EXPIRE_DAYS)
    payload = {"sub": account_id, "aud": CANDIDATE_TOKEN_AUDIENCE, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_candidate(token: Optional[str] = Depends(_candidate_scheme)):
    creds_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification candidat requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise creds_error
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], audience=CANDIDATE_TOKEN_AUDIENCE
        )
        account_id = payload.get("sub")
        if not account_id or not ObjectId.is_valid(account_id):
            raise creds_error
    except JWTError:
        raise creds_error

    db = get_database()
    account = await db["candidate_accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise creds_error
    return account


@router.post("/register", response_model=CandidateAccountOut, status_code=201)
async def candidate_register(payload: CandidateAccountCreate = Body(...)):
    db = get_database()
    email = payload.email.strip().lower()

    existing = await db["candidate_accounts"].find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet email.")

    account_id_short = f"ACC-{secrets.token_hex(4).upper()}"
    now = datetime.utcnow()
    doc = {
        "email": email,
        "hashed_password": get_password_hash(payload.password),
        "first_name": payload.first_name.strip(),
        "last_name": payload.last_name.strip(),
        "phone": (payload.phone or "").strip() or None,
        "profile": (payload.profile or "").strip() or None,
        "date_of_birth": (payload.date_of_birth or "").strip() or None,
        "account_id": account_id_short,
        "created_at": now,
        "must_change_password": False,
    }
    result = await db["candidate_accounts"].insert_one(doc)
    return CandidateAccountOut(
        id=str(result.inserted_id),
        account_id=account_id_short,
        email=email,
        first_name=doc["first_name"],
        last_name=doc["last_name"],
        phone=doc["phone"],
        profile=doc["profile"],
        date_of_birth=doc["date_of_birth"],
        created_at=now.isoformat(),
    )


@router.post("/login", response_model=CandidateLoginOut)
async def candidate_login(payload: CandidateLoginIn = Body(...)):
    db = get_database()
    email = payload.email.strip().lower()

    account = await db["candidate_accounts"].find_one({"email": email})
    if not account or not verify_password(payload.password, account.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Email ou mot de passe invalide")

    account_id = str(account["_id"])
    token = create_candidate_token(account_id)
    return CandidateLoginOut(
        access_token=token,
        account_id=account_id,
        must_change_password=bool(account.get("must_change_password", False)),
    )


_GENERIC_FORGOT_MESSAGE = (
    "Si un compte correspond à cet email, un nouveau mot de passe "
    "provisoire vient d’être envoyé."
)


@router.post("/forgot-password", response_model=CandidateForgotPasswordOut)
async def candidate_forgot_password(payload: CandidateForgotPasswordIn = Body(...)):
    db = get_database()
    email = payload.email.strip().lower()
    if not email:
        return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)

    account = await db["candidate_accounts"].find_one({"email": email})
    if not account:
        return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)

    new_password = secrets.token_urlsafe(6)[:8]
    await db["candidate_accounts"].update_one(
        {"_id": account["_id"]},
        {"$set": {
            "hashed_password": get_password_hash(new_password),
            "must_change_password": True,
            "password_reset_at": datetime.utcnow(),
        }},
    )

    try:
        from email_service import notify_candidate_password_reset
        full_name = f"{account.get('first_name', '')} {account.get('last_name', '')}".strip() or "Candidat"
        notify_candidate_password_reset(
            email,
            full_name,
            account.get("account_id", ""),
            new_password,
        )
    except Exception as e:
        print(f"[EMAIL] Password reset email failed for {email}: {e}")

    return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)


@router.post("/change-password", response_model=CandidateLoginOut)
async def candidate_change_password(
    payload: CandidateChangePasswordIn = Body(...),
    candidate=Depends(get_current_candidate),
):
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=400,
            detail="Le nouveau mot de passe doit être différent de l’ancien.",
        )

    if not verify_password(payload.current_password, candidate.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")

    db = get_database()
    new_hash = get_password_hash(payload.new_password)
    await db["candidate_accounts"].update_one(
        {"_id": candidate["_id"]},
        {"$set": {
            "hashed_password": new_hash,
            "must_change_password": False,
            "password_changed_at": datetime.utcnow(),
        }},
    )

    account_id = str(candidate["_id"])
    token = create_candidate_token(account_id)
    return CandidateLoginOut(
        access_token=token,
        account_id=account_id,
        must_change_password=False,
    )
