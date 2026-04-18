"""
Routes pour les comptes candidats (nouveau système).

Flux :
1. Le candidat crée son compte avec ses informations personnelles
2. Il se connecte avec email + mot de passe
3. Il consulte les sessions disponibles
4. Il soumet une candidature (documents + type seulement)
5. Un dossier (Response) est créé — ID compte ≠ N° dossier
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
from utils.security import SECRET_KEY, ALGORITHM, verify_password, get_password_hash

router = APIRouter()

AUDIENCE = "candidat_account"
TOKEN_EXPIRE_DAYS = 30

_scheme = OAuth2PasswordBearer(tokenUrl="/api/account/login", auto_error=False)


# ── Pydantic models ────────────────────────────────────────────

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    nom: str
    prenom: str
    telephone: str
    date_naissance: Optional[str] = None
    lieu_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    adresse: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account_id: str
    must_change_password: bool = False


class UpdateIn(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    date_naissance: Optional[str] = None
    lieu_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    adresse: Optional[str] = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class CandidatureIn(BaseModel):
    session_id: str
    certification: str
    exam_mode: str
    exam_type: str
    cv: Optional[str] = None
    piece_identite: Optional[str] = None
    justificatif_experience: Optional[str] = None
    diplomes: Optional[str] = None
    amenagement_special: Optional[str] = None


class ResubmitDocIn(BaseModel):
    document_name: str
    file_url: str


# ── Helpers ────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "account_number": doc.get("account_number", ""),
        "email": doc.get("email", ""),
        "nom": doc.get("nom", ""),
        "prenom": doc.get("prenom", ""),
        "telephone": doc.get("telephone"),
        "date_naissance": doc.get("date_naissance"),
        "lieu_naissance": doc.get("lieu_naissance"),
        "nationalite": doc.get("nationalite"),
        "adresse": doc.get("adresse"),
        "created_at": (
            doc["created_at"].isoformat()
            if isinstance(doc.get("created_at"), datetime)
            else doc.get("created_at", "")
        ),
        "must_change_password": bool(doc.get("must_change_password", False)),
    }


def _serialize_dossier(doc: dict, session_name: Optional[str] = None) -> dict:
    answers = doc.get("answers") or {}
    submitted = doc.get("submitted_at")
    return {
        "_id": str(doc["_id"]),
        "public_id": doc.get("public_id"),
        "status": doc.get("status"),
        "session_id": doc.get("session_id"),
        "session_name": session_name,
        "certification": answers.get("Certification souhaitée"),
        "exam_mode": doc.get("exam_mode"),
        "submitted_at": submitted.isoformat() if isinstance(submitted, datetime) else submitted,
        "final_grade": doc.get("final_grade"),
        "final_appreciation": doc.get("final_appreciation"),
        "exam_status": doc.get("exam_status"),
        "documents_validation": doc.get("documents_validation") or {},
        "answers": answers,
    }


def _make_token(account_id: str) -> str:
    exp = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": account_id, "aud": AUDIENCE, "exp": exp},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


async def _next_account_number(db) -> str:
    year = str(datetime.utcnow().year)[2:]
    res = await db["counters"].find_one_and_update(
        {"_id": "candidat_account_seq"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = res.get("seq", 1)
    return f"CAN-{year}-{seq:04d}"


async def get_current_account(token: Optional[str] = Depends(_scheme)):
    err = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise err
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], audience=AUDIENCE)
        aid = payload.get("sub")
        if not aid or not ObjectId.is_valid(aid):
            raise err
    except JWTError:
        raise err
    db = get_database()
    account = await db["candidat_accounts"].find_one({"_id": ObjectId(aid)})
    if not account:
        raise err
    return account


# ── Auth ───────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(payload: RegisterIn = Body(...)):
    db = get_database()
    email = payload.email.strip().lower()
    if await db["candidat_accounts"].find_one({"email": email}):
        raise HTTPException(409, "Un compte existe déjà avec cet email.")

    account_number = await _next_account_number(db)
    now = datetime.utcnow()
    doc = {
        "account_number": account_number,
        "email": email,
        "hashed_password": get_password_hash(payload.password),
        "nom": payload.nom.strip(),
        "prenom": payload.prenom.strip(),
        "telephone": (payload.telephone or "").strip(),
        "date_naissance": payload.date_naissance,
        "lieu_naissance": payload.lieu_naissance,
        "nationalite": payload.nationalite,
        "adresse": payload.adresse,
        "is_active": True,
        "must_change_password": False,
        "created_at": now,
        "updated_at": now,
    }
    result = await db["candidat_accounts"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn = Body(...)):
    db = get_database()
    account = await db["candidat_accounts"].find_one({"email": payload.email.strip().lower()})
    if not account or not verify_password(payload.password, account.get("hashed_password", "")):
        raise HTTPException(401, "Identifiants invalides")
    if not account.get("is_active", True):
        raise HTTPException(403, "Compte désactivé.")
    return LoginOut(
        access_token=_make_token(str(account["_id"])),
        account_id=str(account["_id"]),
        must_change_password=bool(account.get("must_change_password", False)),
    )


@router.get("/me")
async def me(account=Depends(get_current_account)):
    return _serialize(account)


@router.patch("/me")
async def update_me(payload: UpdateIn = Body(...), account=Depends(get_current_account)):
    db = get_database()
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if data:
        data["updated_at"] = datetime.utcnow()
        await db["candidat_accounts"].update_one({"_id": account["_id"]}, {"$set": data})
    updated = await db["candidat_accounts"].find_one({"_id": account["_id"]})
    return _serialize(updated)


@router.post("/change-password", response_model=LoginOut)
async def change_password(payload: ChangePasswordIn = Body(...), account=Depends(get_current_account)):
    if not verify_password(payload.current_password, account.get("hashed_password", "")):
        raise HTTPException(401, "Mot de passe actuel incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(400, "Le nouveau mot de passe doit être différent.")
    db = get_database()
    await db["candidat_accounts"].update_one(
        {"_id": account["_id"]},
        {"$set": {
            "hashed_password": get_password_hash(payload.new_password),
            "must_change_password": False,
            "password_changed_at": datetime.utcnow(),
        }},
    )
    return LoginOut(
        access_token=_make_token(str(account["_id"])),
        account_id=str(account["_id"]),
        must_change_password=False,
    )


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn = Body(...)):
    _msg = "Si un compte correspond à cet email, un mot de passe provisoire vient d\'&être envoyé."
    db = get_database()
    account = await db["candidat_accounts"].find_one({"email": payload.email.strip().lower()})
    if not account:
        return {"message": _msg}
    new_pwd = secrets.token_urlsafe(6)[:8]
    await db["candidat_accounts"].update_one(
        {"_id": account["_id"]},
        {"$set": {
            "hashed_password": get_password_hash(new_pwd),
            "must_change_password": True,
            "password_reset_at": datetime.utcnow(),
        }},
    )
    try:
        from email_service import notify_candidate_password_reset
        notify_candidate_password_reset(
            account.get("email", ""),
            f"{account.get('prenom', '')} {account.get('nom', '')}".strip(),
            account.get("account_number", ""),
            new_pwd,
        )
    except Exception as e:
        print(f"[EMAIL] forgot-password failed: {e}")
    return {"message": _msg}


# ── Sessions ──────────────────────────────────────────────────

@router.get("/sessions")
async def browse_sessions(account=Depends(get_current_account)):
    db = get_database()
    result = []
    async for s in db["sessions"].find({"status": "active"}).sort("created_at", -1):
        result.append({
            "_id": str(s["_id"]),
            "name": s.get("name", ""),
            "description": s.get("description"),
            "start_date": s.get("start_date").isoformat() if isinstance(s.get("start_date"), datetime) else s.get("start_date"),
            "end_date": s.get("end_date").isoformat() if isinstance(s.get("end_date"), datetime) else s.get("end_date"),
            "status": s.get("status"),
        })
    return result


# ── Candidatures ───────────────────────────────────────────────

@router.post("/candidatures", status_code=201)
async def submit_candidature(payload: CandidatureIn = Body(...), account=Depends(get_current_account)):
    db = get_database()
    if not ObjectId.is_valid(payload.session_id):
        raise HTTPException(400, "Session invalide")
    session = await db["sessions"].find_one({"_id": ObjectId(payload.session_id)})
    if not session:
        raise HTTPException(404, "Session introuvable")
    if session.get("status") != "active":
        raise HTTPException(400, "Cette session n'est plus ouverte.")
    existing = await db["responses"].find_one({
        "candidat_account_id": str(account["_id"]),
        "session_id": payload.session_id,
        "status": {"$in": ["pending", "approved"]},
    })
    if existing:
        raise HTTPException(409, "Vous avez déjà une candidature active pour cette session.")

    year = str(datetime.utcnow().year)[2:]
    seq = session.get("sequence_number", 1)
    mode_char = "L" if payload.exam_mode == "online" else "P"
    updated_session = await db["sessions"].find_one_and_update(
        {"_id": session["_id"]},
        {"$inc": {"candidate_counter": 1}},
        return_document=True,
    )
    counter = updated_session.get("candidate_counter", 1)
    public_id = f"IC{year}D{seq:02d}{mode_char}-{counter:04d}"

    nom_complet = f"{account.get('prenom', '')} {account.get('nom', '')}".strip()
    now = datetime.utcnow()
    answers = {
        "Nom complet": nom_complet,
        "Email": account.get("email", ""),
        "Téléphone": account.get("telephone", ""),
        "Date de naissance": account.get("date_naissance") or "",
        "Lieu de naissance": account.get("lieu_naissance") or "",
        "Nationalité": account.get("nationalite") or "",
        "Adresse": account.get("adresse") or "",
        "Certification souhaitée": payload.certification,
        "Mode d'examen": "En ligne" if payload.exam_mode == "online" else "En présentiel",
        "Type d'examen": "Examen direct" if payload.exam_type == "direct" else "Examen après formation IRISQ",
    }
    if payload.cv:
        answers["CV"] = payload.cv
    if payload.piece_identite:
        answers["Pièce d'identité"] = payload.piece_identite
    if payload.justificatif_experience:
        answers["Justificatif d'expérience"] = payload.justificatif_experience
    if payload.diplomes:
        answers["Diplômes"] = payload.diplomes
    if payload.amenagement_special:
        answers["Aménagement spécial"] = payload.amenagement_special

    doc = {
        "candidat_account_id": str(account["_id"]),
        "form_id": None,
        "session_id": payload.session_id,
        "name": nom_complet,
        "email": account.get("email", ""),
        "profile": account.get("nom", ""),
        "answers": answers,
        "status": "pending",
        "public_id": public_id,
        "exam_mode": payload.exam_mode,
        "exam_type": payload.exam_type,
        "submitted_at": now,
        "updated_at": now,
    }
    result = await db["responses"].insert_one(doc)
    return {
        "_id": str(result.inserted_id),
        "public_id": public_id,
        "status": "pending",
        "session_name": session.get("name", ""),
        "certification": payload.certification,
        "submitted_at": now.isoformat(),
    }


@router.get("/candidatures")
async def list_candidatures(account=Depends(get_current_account)):
    db = get_database()
    result = []
    async for doc in db["responses"].find(
        {"candidat_account_id": str(account["_id"])}
    ).sort("submitted_at", -1):
        session_name = None
        sid = doc.get("session_id")
        if sid and ObjectId.is_valid(sid):
            try:
                s = await db["sessions"].find_one({"_id": ObjectId(sid)})
                if s:
                    session_name = s.get("name")
            except Exception:
                pass
        result.append(_serialize_dossier(doc, session_name))
    return result


@router.post("/candidatures/{dossier_id}/resubmit-document")
async def resubmit_document(
    dossier_id: str,
    payload: ResubmitDocIn = Body(...),
    account=Depends(get_current_account),
):
    db = get_database()
    if not ObjectId.is_valid(dossier_id):
        raise HTTPException(400, "ID de dossier invalide")
    dossier = await db["responses"].find_one({
        "_id": ObjectId(dossier_id),
        "candidat_account_id": str(account["_id"]),
    })
    if not dossier:
        raise HTTPException(404, "Dossier introuvable")
    doc_key = payload.document_name
    validation = dossier.get("documents_validation") or {}
    entry = validation.get(doc_key) or {}
    if not entry.get("resubmit_requested"):
        raise HTTPException(400, "Ce document n'a pas été marqué pour renvoi.")
    now = datetime.utcnow()
    updated_entry = {
        **entry,
        "valid": False,
        "resubmit_requested": False,
        "resubmitted_at": now.isoformat(),
        "previous_url": entry.get("previous_url") or ((dossier.get("answers") or {}).get(doc_key)),
    }
    await db["responses"].update_one(
        {"_id": dossier["_id"]},
        {"$set": {
            f"answers.{doc_key}": payload.file_url,
            f"documents_validation.{doc_key}": updated_entry,
            "updated_at": now,
        }},
    )
    return {"status": "ok", "document": doc_key}
