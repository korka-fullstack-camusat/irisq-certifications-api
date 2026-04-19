from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from bson import ObjectId
from pymongo import ReturnDocument
import secrets

from database import get_database
from routes.candidate_auth import get_current_candidate

router = APIRouter()


class ResubmitDocumentIn(BaseModel):
    dossier_id: str
    document_name: str
    file_url: str


class ApplyIn(BaseModel):
    session_id: Optional[str] = None
    exam_mode: Optional[str] = None  # "online" | "onsite"
    exam_type: Optional[str] = None  # "direct" | "after_formation"
    answers: dict = {}  # documents + autres infos complémentaires


def _serialize_account(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "account_id": doc.get("account_id"),
        "email": doc.get("email"),
        "first_name": doc.get("first_name"),
        "last_name": doc.get("last_name"),
        "phone": doc.get("phone"),
        "profile": doc.get("profile"),
        "date_of_birth": doc.get("date_of_birth"),
        "created_at": (
            doc.get("created_at").isoformat()
            if isinstance(doc.get("created_at"), datetime)
            else doc.get("created_at")
        ),
        "must_change_password": bool(doc.get("must_change_password", False)),
    }


def _serialize_dossier(doc: dict) -> dict:
    return {
        "_id": str(doc["_id"]),
        "public_id": doc.get("public_id"),
        "candidate_id": doc.get("candidate_id"),
        "form_id": doc.get("form_id"),
        "account_id": doc.get("account_id"),
        "status": doc.get("status"),
        "session_id": doc.get("session_id"),
        "submitted_at": (
            doc.get("submitted_at").isoformat()
            if isinstance(doc.get("submitted_at"), datetime)
            else doc.get("submitted_at")
        ),
        "answers": doc.get("answers") or {},
        "documents_validation": doc.get("documents_validation") or {},
        "exam_status": doc.get("exam_status"),
        "exam_grade": doc.get("exam_grade"),
        "final_grade": doc.get("final_grade"),
        "final_appreciation": doc.get("final_appreciation"),
        "exam_mode": doc.get("exam_mode"),
        "exam_type": doc.get("exam_type"),
    }


@router.get("/me")
async def candidate_me(candidate=Depends(get_current_candidate)):
    return _serialize_account(candidate)


@router.get("/certifications")
async def candidate_certifications(candidate=Depends(get_current_candidate)):
    """Retourne les certifications/formulaires actifs auxquels le candidat peut postuler."""
    db = get_database()
    forms = await db["forms"].find({"status": "active"}).to_list(100)
    return [
        {
            "_id": str(f["_id"]),
            "title": f.get("title"),
            "description": f.get("description"),
            "category": f.get("category"),
            "fields": f.get("fields", []),
        }
        for f in forms
    ]


@router.get("/dossiers")
async def candidate_dossiers(candidate=Depends(get_current_candidate)):
    """Retourne tous les dossiers de candidature du compte."""
    db = get_database()
    account_id = str(candidate["_id"])
    dossiers = (
        await db["responses"]
        .find({"account_id": account_id})
        .sort("submitted_at", -1)
        .to_list(200)
    )
    return [_serialize_dossier(d) for d in dossiers]


@router.post("/apply/{form_id}", status_code=201)
async def candidate_apply(
    form_id: str,
    payload: ApplyIn = Body(...),
    candidate=Depends(get_current_candidate),
):
    """Soumettre une candidature à une certification.
    Les informations personnelles sont pré-remplies depuis le compte.
    Le candidat fournit uniquement les documents et le mode d’examen.
    """
    db = get_database()

    if not ObjectId.is_valid(form_id):
        raise HTTPException(status_code=400, detail="ID de formulaire invalide")

    form = await db["forms"].find_one({"_id": ObjectId(form_id)})
    if not form:
        raise HTTPException(status_code=404, detail="Certification introuvable")
    if form.get("status") != "active":
        raise HTTPException(
            status_code=400,
            detail="Cette certification n’est pas ouverte aux candidatures",
        )

    account_id = str(candidate["_id"])
    full_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
    email = candidate.get("email", "")
    profile = candidate.get("profile") or ""

    now = datetime.utcnow()

    # Validation session et allocation du numéro de séquence candidat
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

    # Codification du matricule : IC{AA}D{SEQ:02d}{MODE}-{CAND:04d}
    exam_mode = (payload.exam_mode or "").strip().lower()
    mode_letter = "L" if exam_mode == "online" else "P" if exam_mode == "onsite" else ""

    if session_seq and candidate_seq:
        year_suffix = now.strftime("%y")
        public_id = f"IC{year_suffix}D{session_seq:02d}{mode_letter}-{candidate_seq:04d}"
    else:
        public_id = f"IC{now.strftime('%y')}D00{mode_letter}-{secrets.token_hex(2).upper()}"

    candidate_id = f"CAND-{secrets.token_hex(3).upper()}"
    exam_token = secrets.token_urlsafe(32)

    # Fusion infos du compte + documents fournis par le candidat
    answers = dict(payload.answers)
    if not answers.get("Certification souhaitée"):
        answers["Certification souhaitée"] = form.get("title", "")

    response_dict = {
        "form_id": form_id,
        "session_id": session_id,
        "account_id": account_id,
        "name": full_name,
        "email": email,
        "profile": profile,
        "phone": candidate.get("phone"),
        "date_of_birth": candidate.get("date_of_birth"),
        "answers": answers,
        "status": "pending",
        "public_id": public_id,
        "candidate_id": candidate_id,
        "exam_token": exam_token,
        "exam_mode": payload.exam_mode,
        "exam_type": payload.exam_type,
        "submitted_at": now,
    }

    new_response = await db["responses"].insert_one(response_dict)
    await db["forms"].update_one(
        {"_id": ObjectId(form_id)},
        {"$inc": {"responses_count": 1}, "$set": {"updated_at": now}},
    )

    try:
        from email_service import notify_rh_new_submission, notify_candidate_submission_received
        certification = answers.get("Certification souhaitée", "Non spécifiée")
        notify_rh_new_submission(candidate_id, full_name, certification)
        if email:
            notify_candidate_submission_received(email, full_name, public_id, certification, "")
    except Exception as e:
        print(f"[EMAIL] Notification failed but submission saved: {e}")

    created = await db["responses"].find_one({"_id": new_response.inserted_id})
    return _serialize_dossier(created)


@router.post("/resubmit-document")
async def candidate_resubmit_document(
    payload: ResubmitDocumentIn = Body(...),
    candidate=Depends(get_current_candidate),
):
    if not payload.file_url or not payload.document_name or not payload.dossier_id:
        raise HTTPException(status_code=400, detail="dossier_id, document_name et file_url requis")

    if not ObjectId.is_valid(payload.dossier_id):
        raise HTTPException(status_code=400, detail="ID de dossier invalide")

    db = get_database()
    account_id = str(candidate["_id"])

    dossier = await db["responses"].find_one({
        "_id": ObjectId(payload.dossier_id),
        "account_id": account_id,
    })
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier introuvable")

    doc_key = payload.document_name
    now = datetime.utcnow()

    validation = dossier.get("documents_validation") or {}
    entry = validation.get(doc_key) or {}
    if not entry.get("resubmit_requested"):
        raise HTTPException(
            status_code=400,
            detail="Ce document n’a pas été marqué pour renvoi par l’administration.",
        )

    updated_entry = {
        **entry,
        "valid": False,
        "resubmit_requested": False,
        "resubmitted_at": now.isoformat(),
        "previous_url": entry.get("previous_url")
        or ((dossier.get("answers") or {}).get(doc_key)),
    }

    await db["responses"].update_one(
        {"_id": dossier["_id"]},
        {
            "$set": {
                f"answers.{doc_key}": payload.file_url,
                f"documents_validation.{doc_key}": updated_entry,
                "updated_at": now,
            }
        },
    )
    updated = await db["responses"].find_one({"_id": dossier["_id"]})
    return _serialize_dossier(updated)
