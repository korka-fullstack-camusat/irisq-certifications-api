from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_database
from dependencies.auth import require_role

router = APIRouter()

COLLECTION = "admin_documents"

CATEGORIES = [
    "Conditions de validation",
    "Guide candidat",
    "Règlement d'examen",
    "Formulaire",
    "Autre",
]


def _serialize(doc: dict) -> dict:
    return {
        "_id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "category": doc.get("category", ""),
        "file_url": doc.get("file_url", ""),
        "original_name": doc.get("original_name", ""),
        "uploaded_by": doc.get("uploaded_by", ""),
        "uploaded_at": doc["uploaded_at"].isoformat() if doc.get("uploaded_at") else None,
    }


class AdminDocumentIn(BaseModel):
    title: str
    description: Optional[str] = ""
    category: Optional[str] = ""
    file_url: str
    original_name: Optional[str] = ""


@router.get("/admin-documents")
async def list_admin_documents():
    """Liste tous les documents officiels — accessible admin + candidats."""
    db = get_database()
    docs = await db[COLLECTION].find().sort("uploaded_at", -1).to_list(length=200)
    return [_serialize(d) for d in docs]


@router.get("/admin-documents/categories")
async def get_categories():
    return CATEGORIES


@router.post("/admin-documents", status_code=201)
async def create_admin_document(
    payload: AdminDocumentIn,
    current_user=Depends(require_role(["RH", "EVALUATEUR"])),
):
    """Crée un nouveau document officiel — admin seulement."""
    db = get_database()
    doc = {
        **payload.dict(),
        "uploaded_by": current_user.email,
        "uploaded_at": datetime.utcnow(),
    }
    result = await db[COLLECTION].insert_one(doc)
    created = await db[COLLECTION].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/admin-documents/{doc_id}")
async def update_admin_document(
    doc_id: str,
    payload: AdminDocumentIn,
    current_user=Depends(require_role(["RH", "EVALUATEUR"])),
):
    """Met à jour un document officiel."""
    if not ObjectId.is_valid(doc_id):
        raise HTTPException(status_code=400, detail="ID invalide")
    db = get_database()
    update = {k: v for k, v in payload.dict().items() if v is not None}
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document introuvable")
    updated = await db[COLLECTION].find_one({"_id": ObjectId(doc_id)})
    return _serialize(updated)


@router.delete("/admin-documents/{doc_id}", status_code=204)
async def delete_admin_document(
    doc_id: str,
    current_user=Depends(require_role(["RH", "EVALUATEUR"])),
):
    """Supprime un document officiel."""
    if not ObjectId.is_valid(doc_id):
        raise HTTPException(status_code=400, detail="ID invalide")
    db = get_database()
    result = await db[COLLECTION].delete_one({"_id": ObjectId(doc_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return None
