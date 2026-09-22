from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from bson import ObjectId
from database import get_database
from models.formation import FormationCreate, FormationUpdate, FormationOut
from dependencies.auth import require_role

router = APIRouter()


def _fmt(f: dict) -> FormationOut:
    created = f.get("created_at")
    return FormationOut(
        id=str(f["_id"]),
        title=f.get("title", ""),
        description=f.get("description"),
        is_active=f.get("is_active", True),
        created_at=created.isoformat() if isinstance(created, datetime) else created,
    )


@router.get("", response_model=list[FormationOut])
async def list_formations(active_only: bool = False):
    """Liste des formations — public pour le formulaire de demande."""
    db = get_database()
    query: dict = {}
    if active_only:
        query["is_active"] = True
    formations = await db["formations"].find(query).sort("created_at", -1).to_list(500)
    return [_fmt(f) for f in formations]


@router.post("", response_model=FormationOut)
async def create_formation(
    payload: FormationCreate,
    _=Depends(require_role(["RH"])),
):
    db = get_database()
    existing = await db["formations"].find_one({"title": payload.title})
    if existing:
        raise HTTPException(status_code=400, detail="Une formation avec ce titre existe déjà.")
    doc = payload.model_dump()
    doc["created_at"] = datetime.utcnow()
    result = await db["formations"].insert_one(doc)
    created = await db["formations"].find_one({"_id": result.inserted_id})
    return _fmt(created)


@router.put("/{formation_id}", response_model=FormationOut)
async def update_formation(
    formation_id: str,
    payload: FormationUpdate,
    _=Depends(require_role(["RH"])),
):
    db = get_database()
    try:
        oid = ObjectId(formation_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide.")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour.")
    result = await db["formations"].update_one({"_id": oid}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Formation introuvable.")
    updated = await db["formations"].find_one({"_id": oid})
    return _fmt(updated)


@router.delete("/{formation_id}")
async def delete_formation(
    formation_id: str,
    _=Depends(require_role(["RH"])),
):
    db = get_database()
    try:
        oid = ObjectId(formation_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide.")
    result = await db["formations"].delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Formation introuvable.")
    return {"message": "Formation supprimée."}
