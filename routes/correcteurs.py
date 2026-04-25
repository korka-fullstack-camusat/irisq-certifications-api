from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from database import get_database
from models.user import UserCreate, UserInDB, UserOut
from utils.security import get_password_hash
from dependencies.auth import require_role, _invalidate_user_cache, get_current_user
from bson import ObjectId
from datetime import datetime
from typing import List
from pydantic import BaseModel
import secrets
from email_service import (
    notify_correcteur_assignment,
    notify_evaluateur_correction_signed,
    notify_correcteur_relance,
)

router = APIRouter()

EVALUATEUR_ONLY = require_role(["EVALUATEUR"])
CORRECTEUR_ONLY = require_role(["CORRECTEUR"])


def _serialize(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user.get("full_name"),
        "role": user["role"],
        "is_active": user.get("is_active", True),
        "correction_signed_at": user.get("correction_signed_at"),
        "created_at": user.get("created_at"),
    }


# ─── Liste ────────────────────────────────────────────────────────────────────

@router.get("/correcteurs")
async def list_correcteurs(current_user=Depends(EVALUATEUR_ONLY)):
    db = get_database()
    users = await db["users"].find({"role": "CORRECTEUR"}).to_list(length=500)
    return [_serialize(u) for u in users]


# ─── Création ─────────────────────────────────────────────────────────────────

@router.post("/correcteurs", status_code=status.HTTP_201_CREATED)
async def create_correcteur(payload: UserCreate, current_user=Depends(EVALUATEUR_ONLY)):
    if payload.role != "CORRECTEUR":
        raise HTTPException(status_code=400, detail="Le rôle doit être CORRECTEUR")

    db = get_database()
    email = payload.email.lower().strip()

    if await db["users"].find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    new_user = UserInDB(
        email=email,
        hashed_password=get_password_hash(payload.password),
        role="CORRECTEUR",
        full_name=payload.full_name,
        created_at=datetime.utcnow(),
        is_active=True,
    )
    result = await db["users"].insert_one(new_user.model_dump())
    return {
        "id": str(result.inserted_id),
        "email": email,
        "full_name": payload.full_name,
        "role": "CORRECTEUR",
        "is_active": True,
    }


# ─── Activer / désactiver ─────────────────────────────────────────────────────

@router.patch("/correcteurs/{user_id}/toggle")
async def toggle_correcteur_status(user_id: str, current_user=Depends(EVALUATEUR_ONLY)):
    db = get_database()
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    user = await db["users"].find_one({"_id": oid, "role": "CORRECTEUR"})
    if not user:
        raise HTTPException(status_code=404, detail="Correcteur introuvable")

    new_status = not user.get("is_active", True)
    await db["users"].update_one({"_id": oid}, {"$set": {"is_active": new_status}})
    _invalidate_user_cache(user["email"])

    return {"id": user_id, "is_active": new_status}


# ─── Suppression ──────────────────────────────────────────────────────────────

@router.delete("/correcteurs/{user_id}")
async def delete_correcteur(user_id: str, current_user=Depends(EVALUATEUR_ONLY)):
    db = get_database()
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    user = await db["users"].find_one({"_id": oid, "role": "CORRECTEUR"})
    if not user:
        raise HTTPException(status_code=404, detail="Correcteur introuvable")

    if user.get("is_active", True):
        raise HTTPException(status_code=400, detail="Désactivez le compte avant de le supprimer")

    await db["users"].delete_one({"_id": oid})
    _invalidate_user_cache(user["email"])
    return {"id": user_id, "deleted": True}


# ─── Candidatures sans correcteur ─────────────────────────────────────────────

@router.get("/correcteurs/unassigned-responses")
async def unassigned_responses(current_user=Depends(EVALUATEUR_ONLY)):
    db = get_database()
    query = {
        "status": "approved",
        "$or": [
            {"assigned_examiner_email": None},
            {"assigned_examiner_email": {"$exists": False}},
            {"assigned_examiner_email": ""},
        ],
    }
    docs = await db["responses"].find(query).to_list(length=1000)
    return [
        {
            "id": str(d["_id"]),
            "public_id": d.get("public_id"),
            "name": d.get("name"),
            "profile": d.get("profile"),
            "session_id": d.get("session_id"),
            "exam_mode": d.get("exam_mode"),
        }
        for d in docs
    ]


# ─── Assignation en masse ─────────────────────────────────────────────────────

class BulkAssignPayload(BaseModel):
    response_ids: List[str]
    correcteur_email: str


@router.post("/correcteurs/assign-bulk")
async def assign_bulk(
    payload: BulkAssignPayload,
    background_tasks: BackgroundTasks,
    current_user=Depends(EVALUATEUR_ONLY),
):
    db = get_database()

    correcteur = await db["users"].find_one({"email": payload.correcteur_email, "role": "CORRECTEUR"})
    if not correcteur:
        raise HTTPException(status_code=404, detail="Correcteur introuvable")
    if not correcteur.get("is_active", True):
        raise HTTPException(status_code=400, detail="Ce correcteur est désactivé")

    oids = []
    for rid in payload.response_ids:
        try:
            oids.append(ObjectId(rid))
        except Exception:
            raise HTTPException(status_code=400, detail=f"ID invalide : {rid}")

    result = await db["responses"].update_many(
        {"_id": {"$in": oids}},
        {"$set": {"assigned_examiner_email": payload.correcteur_email}},
    )

    # Générer un nouveau mot de passe et l'envoyer par email
    new_password = secrets.token_urlsafe(10)[:12]
    hashed = get_password_hash(new_password)
    await db["users"].update_one(
        {"_id": correcteur["_id"]},
        {"$set": {"hashed_password": hashed, "correction_signed_at": None}},
    )
    _invalidate_user_cache(correcteur["email"])

    full_name = correcteur.get("full_name") or correcteur["email"]
    background_tasks.add_task(
        notify_correcteur_assignment,
        correcteur["email"],
        full_name,
        new_password,
        result.modified_count,
    )

    return {"assigned": result.modified_count}


# ─── Signature des corrections (CORRECTEUR) ───────────────────────────────────

@router.post("/correcteur/sign")
async def sign_corrections(
    background_tasks: BackgroundTasks,
    current_user: UserOut = Depends(CORRECTEUR_ONLY),
):
    db = get_database()

    # Vérifier que toutes les copies assignées sont notées
    assigned = await db["responses"].find(
        {"assigned_examiner_email": current_user.email, "status": "approved"}
    ).to_list(length=1000)

    if not assigned:
        raise HTTPException(status_code=400, detail="Aucune copie assignée")

    pending = [r for r in assigned if not r.get("exam_grade")]
    if pending:
        raise HTTPException(
            status_code=400,
            detail=f"{len(pending)} copie(s) non encore notée(s). Terminez toutes les corrections avant de signer.",
        )

    signed_at = datetime.utcnow()
    await db["users"].update_one(
        {"email": current_user.email},
        {"$set": {"correction_signed_at": signed_at}},
    )
    _invalidate_user_cache(current_user.email)

    # Notifier tous les évaluateurs
    evaluateurs = await db["users"].find({"role": "EVALUATEUR", "is_active": True}).to_list(length=50)
    full_name = current_user.full_name or current_user.email
    for ev in evaluateurs:
        background_tasks.add_task(
            notify_evaluateur_correction_signed,
            ev["email"],
            full_name,
            current_user.email,
            len(assigned),
        )

    return {"signed": True, "signed_at": signed_at.isoformat(), "count": len(assigned)}


# ─── Relancer un correcteur (EVALUATEUR) ──────────────────────────────────────

@router.post("/correcteurs/{user_id}/relancer")
async def relancer_correcteur(
    user_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(EVALUATEUR_ONLY),
):
    db = get_database()
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    correcteur = await db["users"].find_one({"_id": oid, "role": "CORRECTEUR"})
    if not correcteur:
        raise HTTPException(status_code=404, detail="Correcteur introuvable")
    if not correcteur.get("is_active", True):
        raise HTTPException(status_code=400, detail="Ce correcteur est désactivé")

    # Compter les copies non encore notées
    pending = await db["responses"].count_documents({
        "assigned_examiner_email": correcteur["email"],
        "status": "approved",
        "exam_grade": {"$in": [None, ""]},
    })

    if pending == 0:
        raise HTTPException(status_code=400, detail="Ce correcteur n'a aucune copie en attente")

    full_name = correcteur.get("full_name") or correcteur["email"]
    evaluateur_name = current_user.full_name or current_user.email

    background_tasks.add_task(
        notify_correcteur_relance,
        correcteur["email"],
        full_name,
        pending,
        evaluateur_name,
    )

    return {"sent": True, "pending_count": pending}
