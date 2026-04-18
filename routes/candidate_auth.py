"""
Authentification dédiée aux candidats.

Flow:
- À la soumission d'une candidature (routes/responses.py), un mot de passe
  par défaut est généré, haché (bcrypt) et stocké, puis envoyé par email
  au candidat avec son ID Public.
- Le candidat se connecte avec (public_id + password).
- À la première connexion (must_change_password=True), le frontend lui
  impose de changer son mot de passe via POST /api/candidate/change-password.
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
from email_service import notify_candidate_password_reset
from utils.security import SECRET_KEY, ALGORITHM, verify_password, get_password_hash

router = APIRouter()

CANDIDATE_TOKEN_AUDIENCE = "candidate"
CANDIDATE_TOKEN_EXPIRE_DAYS = 14

_candidate_scheme = OAuth2PasswordBearer(tokenUrl="/api/candidate/login", auto_error=False)


class CandidateLoginIn(BaseModel):
    public_id: str
    password: str


class CandidateLoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    response_id: str
    must_change_password: bool = False


class CandidateChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class CandidateForgotPasswordIn(BaseModel):
    public_id: str
    email: EmailStr


class CandidateForgotPasswordOut(BaseModel):
    message: str


def create_candidate_token(response_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=CANDIDATE_TOKEN_EXPIRE_DAYS)
    payload = {"sub": response_id, "aud": CANDIDATE_TOKEN_AUDIENCE, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_candidate(token: Optional[str] = Depends(_candidate_scheme)):
    creds_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Candidate authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise creds_error
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], audience=CANDIDATE_TOKEN_AUDIENCE
        )
        response_id = payload.get("sub")
        if not response_id or not ObjectId.is_valid(response_id):
            raise creds_error
    except JWTError:
        raise creds_error

    db = get_database()
    response = await db["responses"].find_one({"_id": ObjectId(response_id)})
    if not response:
        raise creds_error
    if response.get("credentials_blocked"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre accès a été désactivé suite au refus de votre candidature.",
        )
    return response


@router.post("/login", response_model=CandidateLoginOut)
async def candidate_login(payload: CandidateLoginIn = Body(...)):
    db = get_database()
    public_id = payload.public_id.strip()
    if not public_id or not payload.password:
        raise HTTPException(status_code=400, detail="ID public et mot de passe requis")

    response = await db["responses"].find_one({"public_id": public_id})
    if not response:
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    password_hash = response.get("password_hash")
    if not password_hash or not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    if response.get("credentials_blocked"):
        raise HTTPException(
            status_code=403,
            detail="Votre candidature a été rejetée. Vos identifiants ont été désactivés.",
        )

    response_id = str(response["_id"])
    token = create_candidate_token(response_id)
    return CandidateLoginOut(
        access_token=token,
        response_id=response_id,
        must_change_password=bool(response.get("must_change_password", False)),
    )


_GENERIC_FORGOT_MESSAGE = (
    "Si un compte correspond à ces informations, un nouveau mot de passe "
    "provisoire vient d'être envoyé à l'adresse email enregistrée."
)


@router.post("/forgot-password", response_model=CandidateForgotPasswordOut)
async def candidate_forgot_password(payload: CandidateForgotPasswordIn = Body(...)):
    """Generate a fresh temporary password and email it to the candidate.

    Always returns the same generic message (even if no record matches)
    to avoid leaking whether a given public_id / email combination exists.
    """
    db = get_database()
    public_id = payload.public_id.strip()
    email = payload.email.strip().lower()

    if not public_id or not email:
        return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)

    response = await db["responses"].find_one({"public_id": public_id})
    if not response:
        return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)

    stored_email = (response.get("email") or "").strip().lower()
    if not stored_email or stored_email != email:
        return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)

    if response.get("credentials_blocked"):
        # Match the login endpoint: explicitly refuse blocked candidates.
        raise HTTPException(
            status_code=403,
            detail="Votre candidature a été rejetée. Vos identifiants ont été désactivés.",
        )

    new_password = secrets.token_urlsafe(6)[:8]
    await db["responses"].update_one(
        {"_id": response["_id"]},
        {"$set": {
            "password_hash": get_password_hash(new_password),
            "must_change_password": True,
            "password_reset_at": datetime.utcnow(),
        }},
    )

    try:
        notify_candidate_password_reset(
            stored_email,
            response.get("name") or "Candidat",
            public_id,
            new_password,
        )
    except Exception as e:
        print(f"[EMAIL] Password reset email failed for {stored_email}: {e}")

    return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)


@router.post("/change-password", response_model=CandidateLoginOut)
async def candidate_change_password(
    payload: CandidateChangePasswordIn = Body(...),
    candidate=Depends(get_current_candidate),
):
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=400,
            detail="Le nouveau mot de passe doit être différent de l'ancien.",
        )

    password_hash = candidate.get("password_hash")
    if not password_hash or not verify_password(payload.current_password, password_hash):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")

    db = get_database()
    new_hash = get_password_hash(payload.new_password)
    await db["responses"].update_one(
        {"_id": candidate["_id"]},
        {"$set": {
            "password_hash": new_hash,
            "must_change_password": False,
            "password_changed_at": datetime.utcnow(),
        }},
    )

    # Rotate the token to invalidate any session tied to the old password state.
    response_id = str(candidate["_id"])
    token = create_candidate_token(response_id)
    return CandidateLoginOut(
        access_token=token,
        response_id=response_id,
        must_change_password=False,
    )
