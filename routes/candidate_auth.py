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

from fastapi import APIRouter, Body, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId

from database import get_database
from email_service import notify_candidate_password_reset
from utils.security import SECRET_KEY, ALGORITHM, verify_password, get_password_hash


def _serialize_response(doc: dict) -> dict:
    submitted = doc.get("submitted_at")
    return {
        "_id": str(doc["_id"]),
        "public_id": doc.get("public_id"),
        "candidate_id": doc.get("candidate_id"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "status": doc.get("status"),
        "session_id": doc.get("session_id"),
        "submitted_at": submitted.isoformat() if hasattr(submitted, "isoformat") else submitted,
        "answers": doc.get("answers") or {},
        "documents_validation": doc.get("documents_validation") or {},
        "exam_status": doc.get("exam_status"),
        "exam_grade": doc.get("exam_grade"),
        "exam_mode": doc.get("exam_mode"),
        "exam_type": doc.get("exam_type"),
        "final_grade": doc.get("final_grade"),
        "final_appreciation": doc.get("final_appreciation"),
        "must_change_password": bool(doc.get("must_change_password", False)),
        "exam_token": doc.get("exam_token"),
    }


def _serialize_exam(doc: dict) -> dict:
    return {
        "_id": str(doc["_id"]),
        "certification": doc.get("certification"),
        "title": doc.get("title"),
        "duration_minutes": doc.get("duration_minutes"),
        "start_time": doc.get("start_time"),
        "session_id": doc.get("session_id"),
        "created_at": doc.get("created_at").isoformat() if hasattr(doc.get("created_at"), "isoformat") else doc.get("created_at"),
    }

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
async def candidate_forgot_password(
    payload: CandidateForgotPasswordIn = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
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

    # Send the email in the background — response returns immediately
    background_tasks.add_task(
        notify_candidate_password_reset,
        stored_email,
        response.get("name") or "Candidat",
        public_id,
        new_password,
    )

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


@router.get("/me")
async def candidate_me(candidate=Depends(get_current_candidate)):
    """Retourne le dossier du candidat connecté."""
    return _serialize_response(candidate)


@router.get("/exam")
async def candidate_exam(candidate=Depends(get_current_candidate)):
    """Retourne le dernier examen publié pour la certification du candidat."""
    certification = (candidate.get("answers") or {}).get("Certification souhaitée")
    if not certification:
        return None
    db = get_database()
    exams = await db["exams"].find(
        {"certification": certification}
    ).sort("created_at", -1).limit(1).to_list(1)
    if not exams:
        return None
    return _serialize_exam(exams[0])


class ResubmitDocumentIn(BaseModel):
    document_name: str
    file_url: str


@router.post("/resubmit-document")
async def resubmit_document(
    payload: ResubmitDocumentIn = Body(...),
    candidate=Depends(get_current_candidate),
):
    """Renvoyer un document demandé par l'administration."""
    db = get_database()

    validation = candidate.get("documents_validation") or {}
    entry = validation.get(payload.document_name) or {}
    if not entry.get("resubmit_requested"):
        raise HTTPException(
            status_code=400,
            detail="Ce document n'a pas été marqué pour renvoi par l'administration.",
        )

    now = datetime.utcnow()
    updated_entry = {
        **entry,
        "valid": False,
        "resubmit_requested": False,
        "resubmitted_at": now.isoformat(),
        "previous_url": entry.get("previous_url")
            or (candidate.get("answers") or {}).get(payload.document_name),
    }

    await db["responses"].update_one(
        {"_id": candidate["_id"]},
        {"$set": {
            f"answers.{payload.document_name}": payload.file_url,
            f"documents_validation.{payload.document_name}": updated_entry,
            "updated_at": now,
        }},
    )
    updated = await db["responses"].find_one({"_id": candidate["_id"]})
    return _serialize_response(updated)
