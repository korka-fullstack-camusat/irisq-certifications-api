from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from database import get_database
from routes.candidate_auth import get_current_candidate

router = APIRouter()


class ResubmitDocumentIn(BaseModel):
    document_name: str
    file_url: str


def _serialize_candidate_response(doc: dict) -> dict:
    return {
        "_id": str(doc["_id"]),
        "public_id": doc.get("public_id"),
        "candidate_id": doc.get("candidate_id"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "status": doc.get("status"),
        "session_id": doc.get("session_id"),
        "submitted_at": doc.get("submitted_at").isoformat() if isinstance(doc.get("submitted_at"), datetime) else doc.get("submitted_at"),
        "answers": doc.get("answers") or {},
        "documents_validation": doc.get("documents_validation") or {},
        "exam_status": doc.get("exam_status"),
        "exam_grade": doc.get("exam_grade"),
        "final_grade": doc.get("final_grade"),
        "final_appreciation": doc.get("final_appreciation"),
        "must_change_password": bool(doc.get("must_change_password", False)),
    }


@router.get("/me")
async def candidate_me(candidate=Depends(get_current_candidate)):
    return _serialize_candidate_response(candidate)


@router.post("/resubmit-document")
async def candidate_resubmit_document(
    payload: ResubmitDocumentIn = Body(...),
    candidate=Depends(get_current_candidate),
):
    if not payload.file_url or not payload.document_name:
        raise HTTPException(status_code=400, detail="document_name et file_url requis")

    db = get_database()
    doc_key = payload.document_name
    now = datetime.utcnow()

    validation = candidate.get("documents_validation") or {}
    entry = validation.get(doc_key) or {}
    if not entry.get("resubmit_requested"):
        raise HTTPException(
            status_code=400,
            detail="Ce document n'a pas été marqué pour renvoi par l'administration.",
        )

    updated_entry = {
        **entry,
        "valid": False,
        "resubmit_requested": False,
        "resubmitted_at": now.isoformat(),
        "previous_url": entry.get("previous_url") or ((candidate.get("answers") or {}).get(doc_key)),
    }

    await db["responses"].update_one(
        {"_id": candidate["_id"]},
        {"$set": {
            f"answers.{doc_key}": payload.file_url,
            f"documents_validation.{doc_key}": updated_entry,
            "updated_at": now,
        }},
    )
    updated = await db["responses"].find_one({"_id": candidate["_id"]})
    return _serialize_candidate_response(updated)
