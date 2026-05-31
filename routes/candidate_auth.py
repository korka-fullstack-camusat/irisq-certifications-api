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
from typing import Optional, List

from fastapi import APIRouter, Body, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId

from database import get_database
from email_service import notify_candidate_password_reset  # noqa: F401 (used inline too)
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
        "final_decision": doc.get("final_decision"),   # "certified" | "rejected" | None
        "exam_appreciation": doc.get("exam_appreciation"),
        "must_change_password": bool(doc.get("must_change_password", False)),
        "exam_token": doc.get("exam_token"),
        # Champs de blocage d'examen — utilisés côté candidat pour détecter
        # si l'évaluateur a débloqué l'accès après un rechargement de page.
        "exam_blocked": doc.get("exam_blocked"),
        "exam_blocked_reason": doc.get("exam_blocked_reason"),
        "exam_blocked_at": (
            doc["exam_blocked_at"].isoformat()
            if hasattr(doc.get("exam_blocked_at"), "isoformat")
            else doc.get("exam_blocked_at")
        ),
    }


def _serialize_exam(doc: dict) -> dict:
    return {
        "_id": str(doc["_id"]),
        "certification": doc.get("certification"),
        "title": doc.get("title"),
        "duration_minutes": doc.get("duration_minutes"),
        "deadline": doc.get("deadline"),           # Date limite de dépôt (YYYY-MM-DD)
        "session_id": doc.get("session_id"),
        "document_url": doc.get("document_url"),          # URL du fichier sujet (PDF/DOCX)
        "exam_content_html": doc.get("exam_content_html", ""),  # HTML fidèle du sujet
        "created_at": doc.get("created_at").isoformat() if hasattr(doc.get("created_at"), "isoformat") else doc.get("created_at"),
        "parsed_questions": doc.get("parsed_questions", []),
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


def create_candidate_token(response_id: str, session_token: str) -> str:
    expire = datetime.utcnow() + timedelta(days=CANDIDATE_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": response_id,
        "aud": CANDIDATE_TOKEN_AUDIENCE,
        "exp": expire,
        "sid": session_token,   # session unique — invalide les autres appareils
    }
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

    # Vérification de session unique : si le JWT contient un sid, il doit
    # correspondre à celui stocké en DB. Une connexion sur un autre appareil
    # met à jour le sid en DB et invalide donc cette session.
    jwt_sid = payload.get("sid")
    db_sid = response.get("session_token")
    if jwt_sid and db_sid and jwt_sid != db_sid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SESSION_INVALIDEE",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return response


@router.post("/login", response_model=CandidateLoginOut)
async def candidate_login(payload: CandidateLoginIn = Body(...)):
    db = get_database()
    public_id = payload.public_id.strip()
    if not public_id or not payload.password:
        raise HTTPException(status_code=400, detail="ID public et mot de passe requis")

    # Récupérer TOUS les documents ayant ce public_id (cas multi-candidatures)
    all_responses = await db["responses"].find({"public_id": public_id}).to_list(20)
    if not all_responses:
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    # Chercher tous les documents dont le mot de passe correspond
    # Prioriser : approved > pending > rejected (pour les multi-formations)
    STATUS_PRIORITY = {"approved": 0, "pending": 1, "rejected": 2}
    matching = [
        doc for doc in all_responses
        if doc.get("password_hash") and verify_password(payload.password, doc.get("password_hash"))
    ]
    matching.sort(key=lambda d: STATUS_PRIORITY.get(d.get("status", ""), 99))
    response = matching[0] if matching else None

    if not response:
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    if response.get("credentials_blocked"):
        raise HTTPException(
            status_code=403,
            detail="Votre candidature a été rejetée. Vos identifiants ont été désactivés.",
        )

    response_id = str(response["_id"])
    public_id = response.get("public_id")

    # Générer un nouveau session_token et le synchroniser sur tous les dossiers
    # du même public_id → invalide toutes les sessions actives sur d'autres appareils.
    new_sid = secrets.token_hex(32)
    await db["responses"].update_many(
        {"public_id": public_id} if public_id else {"_id": response["_id"]},
        {"$set": {"session_token": new_sid, "last_login": datetime.utcnow()}},
    )

    token = create_candidate_token(response_id, new_sid)
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
    background_tasks: BackgroundTasks,
    payload: CandidateForgotPasswordIn = Body(...),
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

    # Récupérer TOUS les documents ayant ce public_id (cas multi-candidatures)
    all_responses = await db["responses"].find({"public_id": public_id}).to_list(20)
    if not all_responses:
        return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)

    # Vérifier que l'email correspond à au moins un document
    matching = [
        r for r in all_responses
        if (r.get("email") or "").strip().lower() == email
    ]
    if not matching:
        return CandidateForgotPasswordOut(message=_GENERIC_FORGOT_MESSAGE)

    # Vérifier qu'aucun n'est bloqué (si tous bloqués → refus)
    if all(r.get("credentials_blocked") for r in matching):
        raise HTTPException(
            status_code=403,
            detail="Votre candidature a été rejetée. Vos identifiants ont été désactivés.",
        )

    # Générer UN seul mot de passe et l'appliquer à TOUS les dossiers du même public_id
    # (évite toute ambiguïté pour les candidats multi-formations)
    new_password = secrets.token_urlsafe(6)[:8]
    new_hash = get_password_hash(new_password)
    await db["responses"].update_many(
        {"public_id": public_id},
        {"$set": {
            "password_hash": new_hash,
            "must_change_password": True,
            "password_reset_at": datetime.utcnow(),
        }},
    )

    response = matching[0]
    # Utiliser l'email stocké en DB (identique à `email` après vérification ci-dessus)
    stored_email = (response.get("email") or email).strip()

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
    public_id = candidate.get("public_id")

    # Nouveau session_token → invalide toutes les autres sessions (autres appareils)
    new_sid = secrets.token_hex(32)

    # Synchroniser mot de passe + session_token sur TOUS les dossiers du même public_id
    await db["responses"].update_many(
        {"public_id": public_id} if public_id else {"_id": candidate["_id"]},
        {"$set": {
            "password_hash": new_hash,
            "must_change_password": False,
            "password_changed_at": datetime.utcnow(),
            "session_token": new_sid,
        }},
    )

    response_id = str(candidate["_id"])
    token = create_candidate_token(response_id, new_sid)
    return CandidateLoginOut(
        access_token=token,
        response_id=response_id,
        must_change_password=False,
    )


@router.get("/me")
async def candidate_me(candidate=Depends(get_current_candidate)):
    """Retourne le dossier actif + tous les dossiers du même public_id (multi-formations)."""
    db = get_database()
    public_id = candidate.get("public_id")

    # Récupérer tous les dossiers liés au même public_id
    if public_id:
        all_docs = await db["responses"].find({"public_id": public_id}).to_list(20)
        # Trier : approved en premier, puis pending, puis rejected
        STATUS_PRIORITY = {"approved": 0, "pending": 1, "rejected": 2}
        all_docs.sort(key=lambda d: STATUS_PRIORITY.get(d.get("status", ""), 99))
        dossiers = [_serialize_response(d) for d in all_docs]
    else:
        dossiers = [_serialize_response(candidate)]

    # Le dossier actif = celui du token (ou le premier par priorité)
    active = _serialize_response(candidate)

    return {**active, "dossiers": dossiers}


@router.get("/exam")
async def candidate_exam(candidate=Depends(get_current_candidate)):
    """Retourne le dernier examen publié pour la certification du candidat (dossier actif)."""
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


@router.get("/exams-all")
async def candidate_exams_all(candidate=Depends(get_current_candidate)):
    """Retourne le dernier examen pour chaque certification du candidat (multi-formations).

    Utilisé par le tableau de bord pour afficher une notification par candidature :
    - examen disponible, déjà soumis, corrigé ou délai expiré.
    """
    db = get_database()
    public_id = candidate.get("public_id")

    # Récupérer tous les dossiers liés à ce compte
    if public_id:
        all_docs = await db["responses"].find({"public_id": public_id}).to_list(20)
    else:
        all_docs = [candidate]

    # Certifications uniques (dans l'ordre des dossiers)
    seen: set = set()
    certifications: list = []
    for doc in all_docs:
        cert = (doc.get("answers") or {}).get("Certification souhaitée")
        if cert and cert not in seen:
            seen.add(cert)
            certifications.append(cert)

    # Pour chaque certification, récupérer le dernier examen
    result = []
    for cert in certifications:
        exams = await db["exams"].find(
            {"certification": cert}
        ).sort("created_at", -1).limit(1).to_list(1)
        if exams:
            result.append(_serialize_exam(exams[0]))

    return result


class ReportBlockedIn(BaseModel):
    reason: str = "Rechargement de page pendant l'examen"


@router.post("/report-blocked")
async def report_blocked(
    payload: ReportBlockedIn = Body(...),
    candidate=Depends(get_current_candidate),
):
    """Enregistre qu'un candidat a été bloqué pendant son examen (ex: rechargement de page).

    Garde-fou anti-cycle : si l'évaluateur a explicitement débloqué l'accès
    (exam_blocked is False), on refuse de le re-bloquer ici afin d'éviter la
    boucle : évaluateur débloque → candidat recharge → report-blocked → re-bloque.
    Le frontend gère ce cas via la valeur renvoyée ("already_unblocked": True).
    """
    db = get_database()
    # Re-fetch le doc frais pour avoir exam_blocked à jour
    fresh = await db["responses"].find_one({"_id": candidate["_id"]})
    if fresh and fresh.get("exam_blocked") is False:
        # L'évaluateur a débloqué → on ne re-bloque pas
        return {"ok": True, "already_unblocked": True}

    await db["responses"].update_one(
        {"_id": candidate["_id"]},
        {"$set": {
            "exam_blocked": True,
            "exam_blocked_reason": payload.reason,
            "exam_blocked_at": datetime.utcnow(),
        }},
    )
    return {"ok": True, "already_unblocked": False}


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


# ──────────────────────────────────────────────────────────────────────────────
# Nouvelle candidature depuis l'espace candidat
# ──────────────────────────────────────────────────────────────────────────────

class NewApplicationIn(BaseModel):
    certification: str
    exam_mode: str = "online"   # "online" | "onsite"
    documents: dict = {}        # {"CV": "https://...", "Pièce d'identité": "...", ...}


@router.post("/new-application", status_code=201)
async def new_application(
    payload: NewApplicationIn = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    candidate=Depends(get_current_candidate),
):
    """
    Soumettre une nouvelle candidature depuis l'espace candidat connecté.

    Le candidat choisit une certification ; le backend réutilise ses informations
    personnelles et son public_id existant pour créer un nouveau dossier lié
    au même compte (même identifiants de connexion).
    """
    db = get_database()
    certification = payload.certification.strip()
    if not certification:
        raise HTTPException(status_code=400, detail="Nom de certification requis")

    # Vérifier l'absence de candidature active pour cette certification
    public_id = candidate.get("public_id")
    existing = await db["responses"].find_one({
        "public_id": public_id,
        "answers.Certification souhaitée": certification,
        "status": {"$nin": ["rejected"]},
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Vous avez déjà une candidature active pour « {certification} ».",
        )

    # Trouver le formulaire dont le titre correspond
    form = await db["forms"].find_one({"title": certification})
    form_id = str(form["_id"]) if form else None

    now = datetime.utcnow()
    name          = candidate.get("name") or ""
    email         = candidate.get("email") or ""
    password_hash = candidate.get("password_hash") or ""
    session_token = candidate.get("session_token") or ""
    exam_mode     = (payload.exam_mode or "online").strip().lower()

    candidate_id = f"CAND-{secrets.token_hex(3).upper()}"
    exam_token   = secrets.token_urlsafe(32)

    # Merge certification + provided document URLs into answers
    doc_keys = {"CV", "Pièce d'identité", "Justificatif d'expérience", "Diplômes"}
    answers = {"Certification souhaitée": certification}
    for k, v in (payload.documents or {}).items():
        if k in doc_keys and v:
            answers[k] = v

    response_doc = {
        "form_id":        form_id,
        "name":           name,
        "email":          email,
        "password_hash":  password_hash,
        "session_token":  session_token,
        "public_id":      public_id,
        "candidate_id":   candidate_id,
        "exam_token":     exam_token,
        "exam_mode":      exam_mode,
        "status":         "pending",
        "must_change_password": False,
        "answers":        answers,
        "submitted_at":   now,
    }

    result = await db["responses"].insert_one(response_doc)
    if form_id:
        await db["forms"].update_one(
            {"_id": form["_id"]},
            {"$inc": {"responses_count": 1}, "$set": {"updated_at": now}},
        )

    created = await db["responses"].find_one({"_id": result.inserted_id})

    # Notification email en arrière-plan
    from email_service import notify_rh_new_submission, notify_candidate_submission_received
    background_tasks.add_task(notify_rh_new_submission, candidate_id, name, certification)
    background_tasks.add_task(notify_candidate_submission_received, email, name, public_id, certification, "")

    return _serialize_response(created)
