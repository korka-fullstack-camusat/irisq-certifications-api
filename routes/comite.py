"""
Routes pour le Comité de Validation (Jury).

Le comité peut :
- Consulter toutes les copies corrigées par les correcteurs
- Ajouter sa propre notation avec annotations (bulles bleues)
- Décider si le candidat est certifié ou non (avec motif de rejet)
- Générer la liste des certifiés
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from bson import ObjectId

from database import get_database
from dependencies.auth import require_role

router = APIRouter()

COMITE_ROLES = require_role(["COMITE", "RH"])


def _serialize(doc: dict) -> dict:
    def iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else v

    return {
        "_id": str(doc["_id"]),
        "public_id": doc.get("public_id"),
        "candidate_id": doc.get("candidate_id"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "status": doc.get("status"),
        "session_id": doc.get("session_id"),
        "submitted_at": iso(doc.get("submitted_at")),
        "answers": doc.get("answers") or {},
        "profile": doc.get("profile"),
        "exam_document": doc.get("exam_document"),
        "exam_grade": doc.get("exam_grade"),
        "exam_appreciation": doc.get("exam_appreciation"),
        "exam_comments": doc.get("exam_comments"),
        "exam_status": doc.get("exam_status"),
        "assigned_examiner_email": doc.get("assigned_examiner_email"),
        "answer_grades": doc.get("answer_grades") or [],
        # Champs jury
        "jury_grade": doc.get("jury_grade"),
        "jury_appreciation": doc.get("jury_appreciation"),
        "jury_comments": doc.get("jury_comments"),
        "jury_answer_grades": doc.get("jury_answer_grades") or [],
        "jury_graded_at": iso(doc.get("jury_graded_at")),
        "jury_graded_by": doc.get("jury_graded_by"),
        # Décision finale
        "final_decision": doc.get("final_decision"),
        "final_grade": doc.get("final_grade"),
        "final_appreciation": doc.get("final_appreciation"),
        "rejection_reason": doc.get("rejection_reason"),
        "is_certified": bool(doc.get("is_certified", False)),
        "decided_at": iso(doc.get("decided_at")),
        "decided_by": doc.get("decided_by"),
        "certified_at": iso(doc.get("certified_at")),
    }


# ─── Liste des copies corrigées ───────────────────────────────────────────────

@router.get("/comite/responses")
async def get_comite_responses(current_user=Depends(COMITE_ROLES)):
    """Retourne toutes les copies ayant été corrigées (exam_grade présent)."""
    db = get_database()
    docs = await db["responses"].find(
        {"status": "approved", "exam_grade": {"$exists": True, "$ne": None}}
    ).sort("submitted_at", -1).to_list(length=1000)
    return [_serialize(d) for d in docs]


# ─── Note du jury ─────────────────────────────────────────────────────────────

class JuryGradeIn(BaseModel):
    jury_grade: str
    jury_appreciation: Optional[str] = None
    jury_comments: Optional[str] = None
    jury_answer_grades: Optional[List[Any]] = []


@router.post("/comite/grade/{response_id}")
async def submit_jury_grade(
    response_id: str,
    payload: JuryGradeIn,
    current_user=Depends(COMITE_ROLES),
):
    """Soumet la note du jury pour une copie (annotations bleues)."""
    if not ObjectId.is_valid(response_id):
        raise HTTPException(status_code=400, detail="ID invalide")

    db = get_database()
    updates = {
        "jury_grade": payload.jury_grade,
        "jury_appreciation": payload.jury_appreciation,
        "jury_comments": payload.jury_comments,
        "jury_answer_grades": payload.jury_answer_grades or [],
        "jury_graded_at": datetime.utcnow(),
        "jury_graded_by": current_user.email,
    }
    result = await db["responses"].find_one_and_update(
        {"_id": ObjectId(response_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Réponse introuvable")
    return _serialize(result)


# ─── Décision finale ──────────────────────────────────────────────────────────

class FinalDecisionIn(BaseModel):
    final_decision: str          # "certified" | "rejected"
    final_grade: Optional[str] = None
    final_appreciation: Optional[str] = None
    rejection_reason: Optional[str] = None


@router.post("/comite/decide/{response_id}")
async def set_final_decision(
    response_id: str,
    payload: FinalDecisionIn,
    current_user=Depends(COMITE_ROLES),
):
    """Définit la décision finale : certifié ou rejeté (avec motif)."""
    if not ObjectId.is_valid(response_id):
        raise HTTPException(status_code=400, detail="ID invalide")
    if payload.final_decision not in ("certified", "rejected"):
        raise HTTPException(
            status_code=400,
            detail="final_decision doit être 'certified' ou 'rejected'",
        )

    db = get_database()
    is_certified = payload.final_decision == "certified"
    updates = {
        "final_decision": payload.final_decision,
        "final_grade": payload.final_grade,
        "final_appreciation": payload.final_appreciation,
        "rejection_reason": None if is_certified else payload.rejection_reason,
        "is_certified": is_certified,
        "decided_at": datetime.utcnow(),
        "decided_by": current_user.email,
    }
    result = await db["responses"].find_one_and_update(
        {"_id": ObjectId(response_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Réponse introuvable")
    return _serialize(result)


# ─── Génération des certifiés ─────────────────────────────────────────────────

@router.post("/comite/generate-certified")
async def generate_certified(current_user=Depends(COMITE_ROLES)):
    """
    Finalise les certifiés : marque certified_at sur toutes les réponses
    ayant final_decision='certified' mais pas encore certified_at.
    """
    db = get_database()
    result = await db["responses"].update_many(
        {
            "final_decision": "certified",
            "is_certified": True,
            "certified_at": {"$exists": False},
        },
        {"$set": {"certified_at": datetime.utcnow()}},
    )
    total = await db["responses"].count_documents({"is_certified": True})
    return {
        "generated": result.modified_count,
        "total_certified": total,
    }
