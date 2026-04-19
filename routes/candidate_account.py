"""
Espace candidat — compte utilisateur.

Flux :
1. Le candidat crée un compte (POST /register) avec email + mot de passe choisi.
2. Il se connecte (POST /login) avec email + mot de passe.
3. Une fois connecté, il voit la liste des certifications disponibles.
4. Il candidate (POST /apply) en fournissant les documents et le mode.
5. Un numéro de dossier (public_id / matricule) lui est attribué automatiquement.
   Ce matricule est distinct de l'identifiant de compte.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from bson import ObjectId
from pymongo import ReturnDocument
from pydantic import BaseModel, Field

from database import get_database
from models.candidate_account import (
    CandidateAccountCreate,
    CandidateAccountUpdate,
    CandidateAccountLoginIn,
    CandidateAccountLoginOut,
    CandidateAccountForgotPasswordIn,
    CandidateAccountChangePasswordIn,
    CandidateApplyIn,
)
from utils.security import SECRET_KEY, ALGORITHM, verify_password, get_password_hash
from email_service import notify_candidate_submission_received, notify_rh_new_submission

router = APIRouter()

ACCOUNT_TOKEN_AUDIENCE = "candidate_account"
ACCOUNT_TOKEN_EXPIRE_DAYS = 30

_account_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/candidate/login", auto_error=False
)


def create_account_token(account_oid: str) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCOUNT_TOKEN_EXPIRE_DAYS)
    payload = {"sub": account_oid, "aud": ACCOUNT_TOKEN_AUDIENCE, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_account(token: Optional[str] = Depends(_account_scheme)):
    creds_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise creds_error
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], audience=ACCOUNT_TOKEN_AUDIENCE
        )
        account_oid = payload.get("sub")
        if not account_oid or not ObjectId.is_valid(account_oid):
            raise creds_error
    except JWTError:
        raise creds_error

    db = get_database()
    account = await db["candidate_accounts"].find_one({"_id": ObjectId(account_oid)})
    if not account:
        raise creds_error
    return account


def _serialize_account(doc: dict) -> dict:
    created = doc.get("created_at")
    return {
        "id": str(doc["_id"]),
        "account_id": doc.get("account_id", ""),
        "email": doc.get("email", ""),
        "first_name": doc.get("first_name", ""),
        "last_name": doc.get("last_name", ""),
        "phone": doc.get("phone"),
        "date_of_birth": doc.get("date_of_birth"),
        "address": doc.get("address"),
        "profile": doc.get("profile"),
        "company": doc.get("company"),
        "nationality": doc.get("nationality"),
        "created_at": created.isoformat() if isinstance(created, datetime) else created,
    }


def _serialize_dossier(doc: dict) -> dict:
    submitted = doc.get("submitted_at")
    return {
        "_id": str(doc["_id"]),
        "public_id": doc.get("public_id"),
        "candidate_id": doc.get("candidate_id"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "status": doc.get("status"),
        "session_id": doc.get("session_id"),
        "submitted_at": submitted.isoformat() if isinstance(submitted, datetime) else submitted,
        "answers": doc.get("answers") or {},
        "documents_validation": doc.get("documents_validation") or {},
        "exam_status": doc.get("exam_status"),
        "exam_grade": doc.get("exam_grade"),
        "final_grade": doc.get("final_grade"),
        "final_appreciation": doc.get("final_appreciation"),
        "exam_mode": doc.get("exam_mode"),
        "exam_type": doc.get("exam_type"),
        "form_id": doc.get("form_id"),
    }


# ─────────────────────────────────────────
# Inscription
# ─────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(payload: CandidateAccountCreate = Body(...)):
    """Créer un nouveau compte candidat."""
    db = get_database()
    email = payload.email.strip().lower()

    existing = await db["candidate_accounts"].find_one({"email": email})
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Un compte existe déjà avec cet email.",
        )

    # Générer un identifiant de compte lisible et unique
    account_id = f"CA-{secrets.token_hex(4).upper()}"
    while await db["candidate_accounts"].find_one({"account_id": account_id}):
        account_id = f"CA-{secrets.token_hex(4).upper()}"

    now = datetime.utcnow()
    doc = {
        "account_id": account_id,
        "email": email,
        "password_hash": get_password_hash(payload.password),
        "first_name": payload.first_name.strip(),
        "last_name": payload.last_name.strip(),
        "phone": payload.phone,
        "date_of_birth": payload.date_of_birth,
        "address": payload.address,
        "profile": payload.profile,
        "company": payload.company,
        "nationality": payload.nationality,
        "created_at": now,
    }
    result = await db["candidate_accounts"].insert_one(doc)
    created = await db["candidate_accounts"].find_one({"_id": result.inserted_id})
    return _serialize_account(created)


# ─────────────────────────────────────────
# Connexion
# ─────────────────────────────────────────

@router.post("/login", response_model=CandidateAccountLoginOut)
async def login(payload: CandidateAccountLoginIn = Body(...)):
    """Connexion avec email + mot de passe."""
    db = get_database()
    email = payload.email.strip().lower()

    account = await db["candidate_accounts"].find_one({"email": email})
    if not account or not verify_password(payload.password, account.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = create_account_token(str(account["_id"]))
    return CandidateAccountLoginOut(
        access_token=token,
        account_id=account.get("account_id", ""),
    )


# ─────────────────────────────────────────
# Profil
# ─────────────────────────────────────────

@router.get("/me")
async def me(account=Depends(get_current_account)):
    """Retourne le compte + la liste de tous les dossiers du candidat."""
    db = get_database()
    dossiers = await db["responses"].find(
        {"candidate_account_id": str(account["_id"])}
    ).sort("submitted_at", -1).to_list(200)

    result = _serialize_account(account)
    result["dossiers"] = [_serialize_dossier(d) for d in dossiers]
    return result


@router.patch("/me")
async def update_me(
    payload: CandidateAccountUpdate = Body(...),
    account=Depends(get_current_account),
):
    """Mettre à jour les informations personnelles du compte."""
    db = get_database()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return _serialize_account(account)
    await db["candidate_accounts"].update_one(
        {"_id": account["_id"]}, {"$set": updates}
    )
    updated = await db["candidate_accounts"].find_one({"_id": account["_id"]})
    return _serialize_account(updated)


# ─────────────────────────────────────────
# Dossiers
# ─────────────────────────────────────────

@router.get("/dossiers")
async def list_dossiers(account=Depends(get_current_account)):
    """Lister tous les dossiers de candidature du compte."""
    db = get_database()
    dossiers = await db["responses"].find(
        {"candidate_account_id": str(account["_id"])}
    ).sort("submitted_at", -1).to_list(200)
    return [_serialize_dossier(d) for d in dossiers]


# ─────────────────────────────────────────
# Candidature
# ─────────────────────────────────────────

@router.post("/apply", status_code=201)
async def apply(
    payload: CandidateApplyIn = Body(...),
    account=Depends(get_current_account),
):
    """
    Candidater à une certification.
    Les informations personnelles sont tirées du compte.
    Le candidat fournit uniquement les documents et le mode d'examen.
    Un matricule (public_id) unique est généré pour ce dossier.
    """
    db = get_database()
    form_id = payload.form_id.strip()

    if not ObjectId.is_valid(form_id):
        raise HTTPException(status_code=400, detail="ID du formulaire invalide")

    form = await db["forms"].find_one({"_id": ObjectId(form_id)})
    if not form:
        raise HTTPException(status_code=404, detail="Certification introuvable")

    # Vérifier si le candidat a déjà postulé à cette certification
    existing = await db["responses"].find_one({
        "candidate_account_id": str(account["_id"]),
        "form_id": form_id,
        "status": {"$nin": ["rejected"]},
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Vous avez déjà une candidature active pour cette certification.",
        )

    # Infos personnelles depuis le compte
    full_name = f"{account.get('first_name', '')} {account.get('last_name', '')}".strip()
    email = account.get("email", "")
    profile = account.get("profile", "")
    certification_name = form.get("title", "Non spécifiée")

    now = datetime.utcnow()
    answers = dict(payload.answers or {})
    answers["Certification souhaitée"] = certification_name

    # Gestion de la session
    session_id = payload.session_id
    session_seq = 0
    candidate_seq = 0
    if session_id:
        if not ObjectId.is_valid(session_id):
            raise HTTPException(status_code=400, detail="ID de session invalide")
        session_doc = await db["sessions"].find_one_and_update(
            {"_id": ObjectId(session_id)},
            {"$inc": {"candidate_counter": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if not session_doc:
            raise HTTPException(status_code=404, detail="Session introuvable")
        session_seq = session_doc.get("sequence_number") or 1
        candidate_seq = session_doc.get("candidate_counter") or 1

    exam_mode = (payload.exam_mode or "").strip().lower()
    mode_letter = "L" if exam_mode == "online" else "P" if exam_mode == "onsite" else ""
    year_suffix = now.strftime("%y")

    if session_seq and candidate_seq:
        public_id = f"IC{year_suffix}D{session_seq:02d}{mode_letter}-{candidate_seq:04d}"
    else:
        public_id = f"IC{year_suffix}D00{mode_letter}-{secrets.token_hex(2).upper()}"

    candidate_id = f"CAND-{secrets.token_hex(3).upper()}"
    exam_token = secrets.token_urlsafe(32)

    response_doc = {
        "form_id": form_id,
        "session_id": session_id,
        "candidate_account_id": str(account["_id"]),
        "name": full_name,
        "email": email,
        "profile": profile,
        "answers": answers,
        "status": "pending",
        "public_id": public_id,
        "candidate_id": candidate_id,
        "exam_token": exam_token,
        "exam_mode": exam_mode,
        "exam_type": payload.exam_type,
        "submitted_at": now,
    }

    result = await db["responses"].insert_one(response_doc)
    await db["forms"].update_one(
        {"_id": ObjectId(form_id)},
        {"$inc": {"responses_count": 1}, "$set": {"updated_at": now}},
    )

    created = await db["responses"].find_one({"_id": result.inserted_id})

    try:
        notify_rh_new_submission(candidate_id, full_name, certification_name)
        notify_candidate_submission_received(email, full_name, public_id, certification_name, "")
    except Exception as e:
        print(f"[EMAIL] Notification failed: {e}")

    return _serialize_dossier(created)


# ─────────────────────────────────────────
# Réenvoi de document
# ─────────────────────────────────────────

class ResubmitDocumentIn(BaseModel):
    dossier_id: str
    document_name: str
    file_url: str


@router.post("/resubmit-document")
async def resubmit_document(
    payload: ResubmitDocumentIn = Body(...),
    account=Depends(get_current_account),
):
    """Renvoyer un document demandé par l'administration pour un dossier spécifique."""
    db = get_database()

    if not ObjectId.is_valid(payload.dossier_id):
        raise HTTPException(status_code=400, detail="ID de dossier invalide")

    dossier = await db["responses"].find_one({
        "_id": ObjectId(payload.dossier_id),
        "candidate_account_id": str(account["_id"]),
    })
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier introuvable")

    validation = dossier.get("documents_validation") or {}
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
            or (dossier.get("answers") or {}).get(payload.document_name),
    }

    await db["responses"].update_one(
        {"_id": dossier["_id"]},
        {"$set": {
            f"answers.{payload.document_name}": payload.file_url,
            f"documents_validation.{payload.document_name}": updated_entry,
            "updated_at": now,
        }},
    )
    updated = await db["responses"].find_one({"_id": dossier["_id"]})
    return _serialize_dossier(updated)


# ─────────────────────────────────────────
# Mot de passe oublié
# ─────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(payload: CandidateAccountForgotPasswordIn = Body(...)):
    """Réinitialiser le mot de passe via email."""
    db = get_database()
    email = payload.email.strip().lower()

    _GENERIC_MSG = (
        "Si un compte correspond à cet email, un nouveau mot de passe provisoire "
        "vient d'être envoyé."
    )

    account = await db["candidate_accounts"].find_one({"email": email})
    if not account:
        return {"message": _GENERIC_MSG}

    new_password = secrets.token_urlsafe(6)[:8]
    await db["candidate_accounts"].update_one(
        {"_id": account["_id"]},
        {"$set": {
            "password_hash": get_password_hash(new_password),
            "must_change_password": True,
            "password_reset_at": datetime.utcnow(),
        }},
    )

    try:
        from email_service import notify_candidate_password_reset
        full_name = f"{account.get('first_name', '')} {account.get('last_name', '')}".strip()
        notify_candidate_password_reset(
            email, full_name, account.get("account_id", ""), new_password
        )
    except Exception as e:
        print(f"[EMAIL] Password reset failed for {email}: {e}")

    return {"message": _GENERIC_MSG}


# ─────────────────────────────────────────
# Changement de mot de passe
# ─────────────────────────────────────────

@router.post("/change-password", response_model=CandidateAccountLoginOut)
async def change_password(
    payload: CandidateAccountChangePasswordIn = Body(...),
    account=Depends(get_current_account),
):
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=400,
            detail="Le nouveau mot de passe doit être différent de l'ancien.",
        )

    if not verify_password(payload.current_password, account.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")

    db = get_database()
    await db["candidate_accounts"].update_one(
        {"_id": account["_id"]},
        {"$set": {
            "password_hash": get_password_hash(payload.new_password),
            "must_change_password": False,
            "password_changed_at": datetime.utcnow(),
        }},
    )

    token = create_account_token(str(account["_id"]))
    return CandidateAccountLoginOut(
        access_token=token,
        account_id=account.get("account_id", ""),
    )


# ─────────────────────────────────────────
# Certifications disponibles (public)
# ─────────────────────────────────────────

@router.get("/certifications")
async def list_certifications():
    """Liste des certifications disponibles — accessible sans authentification."""
    db = get_database()
    forms = await db["forms"].find({}).sort("created_at", -1).to_list(200)
    result = []
    for f in forms:
        created = f.get("created_at")
        result.append({
            "_id": str(f["_id"]),
            "title": f.get("title", ""),
            "description": f.get("description", ""),
            "created_at": created.isoformat() if isinstance(created, datetime) else created,
            "responses_count": f.get("responses_count", 0),
        })
    return result
