"""
Compte candidat dédié (nouveau flux)

Le candidat crée d'abord un compte (identité + contact + mot de passe).
Une fois connecté, il accède à son dashboard où il peut postuler à une
certification. Le code de codification (IC{YY}D{SEQ:02d}{MODE}-{CAND:04d})
n'est généré qu'au moment de la candidature, pas à l'inscription.
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from bson import ObjectId
from pymongo import ReturnDocument

from database import get_database
from models.candidate_account import (
    CandidateRegisterIn, CandidateLoginIn, CandidateLoginOut,
    CandidateAccountOut, CandidateApplyIn,
)
from utils.security import SECRET_KEY, ALGORITHM, verify_password, get_password_hash

router = APIRouter()

ACCOUNT_TOKEN_AUDIENCE = "candidate_account"
ACCOUNT_TOKEN_EXPIRE_DAYS = 14
ACCOUNTS_COLLECTION = "candidate_accounts"

_account_scheme = OAuth2PasswordBearer(tokenUrl="/api/candidate-account/login", auto_error=False)


def _create_account_token(account_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCOUNT_TOKEN_EXPIRE_DAYS)
    payload = {"sub": account_id, "aud": ACCOUNT_TOKEN_AUDIENCE, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_account(token: Optional[str] = Depends(_account_scheme)):
    creds_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification candidat requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise creds_error
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], audience=ACCOUNT_TOKEN_AUDIENCE)
        account_id = payload.get("sub")
        if not account_id or not ObjectId.is_valid(account_id):
            raise creds_error
    except JWTError:
        raise creds_error

    db = get_database()
    account = await db[ACCOUNTS_COLLECTION].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise creds_error
    return account


def _serialize_account(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "nom": doc.get("nom", ""),
        "prenom": doc.get("prenom", ""),
        "email": doc.get("email", ""),
        "telephone": doc.get("telephone", ""),
        "date_naissance": doc.get("date_naissance", ""),
        "lieu_naissance": doc.get("lieu_naissance"),
        "nationalite": doc.get("nationalite"),
        "adresse": doc.get("adresse"),
        "annees_experience": doc.get("annees_experience", ""),
        "created_at": doc.get("created_at") or datetime.utcnow(),
    }


def _serialize_application(doc: dict) -> dict:
    submitted_at = doc.get("submitted_at")
    return {
        "id": str(doc["_id"]),
        "public_id": doc.get("public_id"),
        "status": doc.get("status", "pending"),
        "certification": (doc.get("answers") or {}).get("Certification souhaitée"),
        "exam_mode": doc.get("exam_mode"),
        "exam_type": doc.get("exam_type"),
        "session_id": doc.get("session_id"),
        "submitted_at": submitted_at.isoformat() if isinstance(submitted_at, datetime) else submitted_at,
        "exam_grade": doc.get("exam_grade"),
        "final_grade": doc.get("final_grade"),
        "documents_validation": doc.get("documents_validation") or {},
    }


# ───────────────────────── REGISTER ─────────────────────────

@router.post("/register", response_model=CandidateLoginOut, status_code=201)
async def register_candidate(payload: CandidateRegisterIn = Body(...)):
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=400, detail="Les mots de passe ne correspondent pas.")

    db = get_database()
    email = payload.email.lower().strip()

    existing = await db[ACCOUNTS_COLLECTION].find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email.")

    now = datetime.utcnow()
    account_doc = {
        "nom": payload.nom.strip(),
        "prenom": payload.prenom.strip(),
        "date_naissance": payload.date_naissance.strip(),
        "lieu_naissance": (payload.lieu_naissance or "").strip() or None,
        "nationalite": (payload.nationalite or "").strip() or None,
        "telephone": payload.telephone.strip(),
        "email": email,
        "annees_experience": payload.annees_experience.strip(),
        "adresse": (payload.adresse or "").strip() or None,
        "password_hash": get_password_hash(payload.password),
        "created_at": now,
        "updated_at": now,
    }

    result = await db[ACCOUNTS_COLLECTION].insert_one(account_doc)
    account_id = str(result.inserted_id)
    token = _create_account_token(account_id)
    return CandidateLoginOut(access_token=token, account_id=account_id)


# ───────────────────────── LOGIN ─────────────────────────

@router.post("/login", response_model=CandidateLoginOut)
async def login_candidate(payload: CandidateLoginIn = Body(...)):
    db = get_database()
    email = payload.email.lower().strip()
    account = await db[ACCOUNTS_COLLECTION].find_one({"email": email})
    if not account or not verify_password(payload.password, account.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    account_id = str(account["_id"])
    token = _create_account_token(account_id)
    return CandidateLoginOut(access_token=token, account_id=account_id)


# ───────────────────────── ME ─────────────────────────

@router.get("/me")
async def candidate_me(account=Depends(get_current_account)):
    db = get_database()
    applications = await db["responses"].find(
        {"candidate_account_id": str(account["_id"])}
    ).sort("submitted_at", -1).to_list(200)

    return {
        "account": _serialize_account(account),
        "applications": [_serialize_application(a) for a in applications],
    }


# ───────────────────────── APPLY ─────────────────────────

FORM_TITLE = "Fiche de demande - IRISQ CERTIFICATION"


async def _get_or_create_default_form(db) -> str:
    existing = await db["forms"].find_one({"title": FORM_TITLE})
    if existing:
        return str(existing["_id"])
    now = datetime.utcnow()
    form_doc = {
        "title": FORM_TITLE,
        "description": "PGC-ENR-06-01",
        "category": "Certification",
        "status": "active",
        "fields": [
            {"id": "nom", "type": "text", "label": "Nom", "required": True},
            {"id": "prenom", "type": "text", "label": "Prénom", "required": True},
            {"id": "cert", "type": "text", "label": "Certification souhaitée", "required": True},
        ],
        "responses_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    inserted = await db["forms"].insert_one(form_doc)
    return str(inserted.inserted_id)


@router.post("/apply", status_code=201)
async def apply_for_certification(
    payload: CandidateApplyIn = Body(...),
    account=Depends(get_current_account),
):
    if not payload.declaration_accepted:
        raise HTTPException(status_code=400, detail="Déclaration sur l'honneur requise.")

    if payload.exam_mode not in ("online", "onsite"):
        raise HTTPException(status_code=400, detail="Mode d'examen invalide.")
    if payload.exam_type not in ("direct", "after_formation"):
        raise HTTPException(status_code=400, detail="Type d'examen invalide.")
    if payload.exam_type == "direct" and not payload.attestation_formation_url:
        raise HTTPException(
            status_code=400,
            detail="Attestation de formation obligatoire pour un examen direct.",
        )

    db = get_database()
    form_id = payload.form_id
    if not form_id or not ObjectId.is_valid(form_id):
        form_id = await _get_or_create_default_form(db)

    # Allocate session sequence if a session is specified
    session_id = payload.session_id
    session_seq = 0
    candidate_seq = 0
    if session_id:
        if not ObjectId.is_valid(session_id):
            raise HTTPException(status_code=400, detail="Session invalide.")
        session_doc = await db["sessions"].find_one_and_update(
            {"_id": ObjectId(session_id)},
            {"$inc": {"candidate_counter": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if not session_doc:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        session_seq = session_doc.get("sequence_number") or 1
        candidate_seq = session_doc.get("candidate_counter") or 1

    mode_letter = "L" if payload.exam_mode == "online" else "P"
    now = datetime.utcnow()
    year_suffix = now.strftime("%y")

    if session_seq and candidate_seq:
        public_id = f"IC{year_suffix}D{session_seq:02d}{mode_letter}-{candidate_seq:04d}"
    else:
        count = await db["responses"].count_documents({})
        public_id = f"IC{year_suffix}D01{mode_letter}-{(count + 1):04d}"

    exam_mode_label = "En ligne" if payload.exam_mode == "online" else "Présentiel"
    exam_type_label = "Examen direct" if payload.exam_type == "direct" else "Examen après formation IRISQ"

    response_doc = {
        "form_id": form_id,
        "session_id": session_id or None,
        "candidate_account_id": str(account["_id"]),
        "name": f"{account.get('prenom','')} {account.get('nom','')}".strip(),
        "email": account.get("email"),
        "profile": "Candidat à la Certification",
        "status": "pending",
        "public_id": public_id,
        "candidate_id": f"CAND-{str(account['_id'])[-6:].upper()}",
        "exam_mode": payload.exam_mode,
        "exam_type": payload.exam_type,
        "submitted_at": now,
        "answers": {
            "Nom": account.get("nom", ""),
            "Prénom": account.get("prenom", ""),
            "Date de naissance": account.get("date_naissance", ""),
            "Lieu de naissance": account.get("lieu_naissance", "") or "",
            "Nationalité": account.get("nationalite", "") or "",
            "Adresse": account.get("adresse", "") or "",
            "Téléphone": account.get("telephone", ""),
            "Email": account.get("email", ""),
            "Expérience (années)": account.get("annees_experience", ""),
            "Certification souhaitée": payload.certification,
            "Mode d'examen": exam_mode_label,
            "Type d'examen": exam_type_label,
            "CV": [payload.cv_url] if payload.cv_url else [],
            "Pièce d'identité": [payload.piece_identite_url] if payload.piece_identite_url else [],
            "Justificatif d'expérience": [payload.justificatif_experience_url] if payload.justificatif_experience_url else [],
            "Diplômes": [payload.diplomes_url] if payload.diplomes_url else [],
            "Attestation de formation": [payload.attestation_formation_url] if payload.attestation_formation_url else [],
            "Aménagement spécifique": payload.amenagement or "Non",
            "Détails aménagement": payload.amenagement_details or "N/A",
            "Déclaration acceptée": payload.declaration_accepted,
        },
    }

    inserted = await db["responses"].insert_one(response_doc)
    await db["forms"].update_one(
        {"_id": ObjectId(form_id)},
        {"$inc": {"responses_count": 1}, "$set": {"updated_at": now}},
    )

    saved = await db["responses"].find_one({"_id": inserted.inserted_id})
    return _serialize_application(saved)


# ───────────────────────── APPLICATIONS LIST ─────────────────────────

@router.get("/applications")
async def list_my_applications(account=Depends(get_current_account)):
    db = get_database()
    applications = await db["responses"].find(
        {"candidate_account_id": str(account["_id"])}
    ).sort("submitted_at", -1).to_list(200)
    return [_serialize_application(a) for a in applications]


# ───────────────────────── CERTIFICATIONS / SESSIONS PUBLIQUES ─────────────────────────

CERTIFICATIONS = [
    "Junior Implementor ISO/IEC17025:2017",
    "Implementor ISO/IEC17025:2017",
    "Lead Implementor ISO/IEC17025:2017",
    "Junior Implementor ISO 9001:2015",
    "Implementor ISO 9001:2015",
    "Lead Implementor ISO 9001:2015",
    "Junior Implementor ISO 14001:2015",
    "Implementor ISO 14001:2015",
    "Lead Implementor ISO 14001:2015",
]


@router.get("/certifications")
async def list_certifications(account=Depends(get_current_account)):
    """Liste des certifications disponibles + sessions actives pour le candidat."""
    db = get_database()
    sessions = await db["sessions"].find({"status": "active"}).sort("start_date", 1).to_list(100)
    serialized_sessions = [
        {
            "id": str(s["_id"]),
            "name": s.get("name", ""),
            "description": s.get("description"),
            "start_date": s.get("start_date"),
            "end_date": s.get("end_date"),
            "status": s.get("status"),
        }
        for s in sessions
    ]
    return {
        "certifications": CERTIFICATIONS,
        "sessions": serialized_sessions,
    }
