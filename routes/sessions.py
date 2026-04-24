import io
import re
import zipfile
import json
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import StreamingResponse
from bson import ObjectId
from datetime import datetime
from typing import Optional

from database import get_database, get_fs
from models.session import SessionCreate, SessionUpdate
from models.user import UserOut
from dependencies.auth import require_role
from utils.audit import log_action

router = APIRouter()

DOCUMENT_FIELDS = [
    "CV",
    "Pièce d'identité",
    "Justificatif d'expérience",
    "Diplômes",
]

_SAFE_RE = re.compile(r"[^A-Za-z0-9._\-]+")


def _safe_name(value: str, fallback: str = "inconnu") -> str:
    if not value:
        return fallback
    cleaned = _SAFE_RE.sub("_", value).strip("._") or fallback
    return cleaned[:120]


def _extract_file_id(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return tail if ObjectId.is_valid(tail) else None


def _iter_urls(value):
    if not value:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            if isinstance(v, str):
                yield v


def serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


async def _write_dossiers(zf: zipfile.ZipFile, responses: list, fs) -> None:
    """Write each response as a dossier folder (info.json + documents) into the zip."""
    for r in responses:
        answers = r.get("answers") or {}
        formation_raw = answers.get("Certification souhaitée")
        formation = formation_raw.strip() if isinstance(formation_raw, str) and formation_raw.strip() else "Sans_formation"
        candidate = r.get("name") or r.get("email") or str(r.get("_id"))
        public_id = r.get("public_id") or str(r.get("_id"))
        folder = f"{_safe_name(formation)}/{_safe_name(candidate)}_{_safe_name(public_id, 'id')}"

        summary = {
            "public_id": r.get("public_id"),
            "name": r.get("name"),
            "email": r.get("email"),
            "status": r.get("status"),
            "submitted_at": r.get("submitted_at").isoformat() if isinstance(r.get("submitted_at"), datetime) else r.get("submitted_at"),
            "certification": formation_raw,
            "exam_mode": r.get("exam_mode"),
            "exam_type": r.get("exam_type"),
            "answers": {k: v for k, v in answers.items() if not isinstance(v, (list, dict)) or k not in DOCUMENT_FIELDS},
            "documents_validation": r.get("documents_validation") or {},
        }
        zf.writestr(f"{folder}/info.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))

        for field in DOCUMENT_FIELDS:
            raw = answers.get(field)
            for idx, url in enumerate(_iter_urls(raw)):
                file_id = _extract_file_id(url)
                if not file_id:
                    continue
                try:
                    grid_out = await fs.open_download_stream(ObjectId(file_id))
                    content = await grid_out.read()
                    original = (grid_out.metadata or {}).get("original_name") or grid_out.filename or f"{field}"
                    ext = "." + original.rsplit(".", 1)[-1] if "." in original else ""
                    suffix = f"_{idx+1}" if idx > 0 else ""
                    filename = f"{_safe_name(field)}{suffix}{ext}"
                    zf.writestr(f"{folder}/{filename}", content)
                except Exception:
                    zf.writestr(f"{folder}/{_safe_name(field)}_MANQUANT.txt", f"Fichier introuvable: {url}\n")


@router.get("", response_description="List all sessions (public for /demande-certification)")
async def list_sessions():
    db = get_database()
    sessions = await db["sessions"].find().sort("created_at", -1).to_list(1000)
    return [serialize(s) for s in sessions]


@router.get("/export-all", response_description="Export dossiers across all sessions as ZIP")
async def export_all_dossiers(
    mode: Optional[str] = Query(None, description="Filter by exam_mode: online | onsite"),
    formation: Optional[str] = Query(None, description="Filter by certification name"),
    status: Optional[str] = Query(None, description="Filter by candidature status: approved | rejected | pending"),
    session_id: Optional[str] = Query(None, description="Optional specific session id"),
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()

    query: dict = {}
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode in {"online", "onsite"}:
        query["exam_mode"] = normalized_mode
    normalized_status = (status or "").strip().lower()
    if normalized_status in {"approved", "rejected", "pending"}:
        query["status"] = normalized_status
    if formation:
        query["answers.Certification souhaitée"] = formation
    if session_id:
        query["session_id"] = session_id

    responses = (
        await db["responses"]
        .find(query)
        .sort("submitted_at", -1)
        .to_list(10000)
    )

    fs = get_fs()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        await _write_dossiers(zf, responses, fs)
    buffer.seek(0)

    parts = ["dossiers"]
    if formation:
        parts.append(_safe_name(formation))
    if normalized_mode == "online":
        parts.append("en-ligne")
    elif normalized_mode == "onsite":
        parts.append("presentiel")
    if normalized_status:
        parts.append(normalized_status)
    filename = f"{'_'.join(parts)}_{datetime.utcnow().strftime('%Y%m%d')}.zip"

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_description="Create a new session (admin only)", status_code=201)
async def create_session(
    payload: SessionCreate = Body(...),
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()
    data = payload.model_dump()
    now = datetime.utcnow()
    data["created_at"] = now
    data["updated_at"] = now
    # Sequence number = max existing + 1 (used in dossier codification IC{YY}D{SEQ}-{ID})
    last = await db["sessions"].find_one(
        {"sequence_number": {"$exists": True}},
        sort=[("sequence_number", -1)],
    )
    data["sequence_number"] = (last.get("sequence_number", 0) + 1) if last else 1
    data["candidate_counter"] = 0
    result = await db["sessions"].insert_one(data)
    created = await db["sessions"].find_one({"_id": result.inserted_id})
    await log_action(
        action="session_created",
        resource_type="session",
        resource_id=str(result.inserted_id),
        user_email=current_user.email,
        user_role=current_user.role,
        user_name=current_user.full_name,
        resource_label=payload.name,
        details={"name": payload.name, "status": data.get("status")},
    )
    return serialize(created)


@router.get("/{session_id}", response_description="Get a single session")
async def get_session(session_id: str):
    db = get_database()
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    s = await db["sessions"].find_one({"_id": ObjectId(session_id)})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return serialize(s)


@router.patch("/{session_id}", response_description="Update a session (admin only)")
async def update_session(
    session_id: str,
    payload: SessionUpdate = Body(...),
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    data["updated_at"] = datetime.utcnow()
    result = await db["sessions"].update_one(
        {"_id": ObjectId(session_id)}, {"$set": data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = await db["sessions"].find_one({"_id": ObjectId(session_id)})
    await log_action(
        action="session_updated",
        resource_type="session",
        resource_id=session_id,
        user_email=current_user.email,
        user_role=current_user.role,
        user_name=current_user.full_name,
        resource_label=updated.get("name", session_id),
        details={k: v for k, v in data.items() if k != "updated_at"},
    )
    return serialize(updated)


@router.delete("/{session_id}", response_description="Delete a session (admin only)")
async def delete_session(
    session_id: str,
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    session_doc = await db["sessions"].find_one({"_id": ObjectId(session_id)})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db["sessions"].delete_one({"_id": ObjectId(session_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await log_action(
        action="session_deleted",
        resource_type="session",
        resource_id=session_id,
        user_email=current_user.email,
        user_role=current_user.role,
        user_name=current_user.full_name,
        resource_label=session_doc.get("name", session_id),
    )
    return {"status": "deleted"}


@router.get("/{session_id}/eligibility", response_description="Check if an email can apply to this session")
async def check_session_eligibility(
    session_id: str,
    email: str = Query(..., description="Candidate email to check"),
):
    db = get_database()
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await db["sessions"].find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    existing = await db["responses"].find_one({
        "session_id": session_id,
        "email": {"$regex": f"^{email}$", "$options": "i"},
    })

    if not existing:
        return {"eligible": True}

    if existing.get("status") == "rejected":
        return {
            "eligible": False,
            "code": "APPLICATION_REJECTED",
            "message": "Votre candidature a été rejetée pour cette session. Veuillez attendre l'ouverture d'une prochaine session.",
        }

    return {
        "eligible": False,
        "code": "ALREADY_APPLIED",
        "message": "Vous avez déjà postulé à cette session. Vous ne pouvez pas postuler à nouveau tant que la session est ouverte.",
    }


@router.get("/{session_id}/responses", response_description="List candidatures of a given session")
async def list_session_responses(
    session_id: str,
    current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"])),
):
    db = get_database()
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    responses = (
        await db["responses"]
        .find({"session_id": session_id})
        .sort("submitted_at", -1)
        .to_list(1000)
    )
    return [serialize(r) for r in responses]


@router.get("/{session_id}/export", response_description="Export all dossiers of a session as ZIP")
async def export_session_dossiers(
    session_id: str,
    mode: Optional[str] = Query(None, description="Filter by exam_mode: online | onsite"),
    formation: Optional[str] = Query(None, description="Filter by certification name"),
    status: Optional[str] = Query(None, description="Filter by candidature status: approved | rejected | pending"),
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await db["sessions"].find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    query: dict = {"session_id": session_id}
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode in {"online", "onsite"}:
        query["exam_mode"] = normalized_mode
    normalized_status = (status or "").strip().lower()
    if normalized_status in {"approved", "rejected", "pending"}:
        query["status"] = normalized_status
    if formation:
        query["answers.Certification souhaitée"] = formation

    responses = (
        await db["responses"]
        .find(query)
        .sort("submitted_at", -1)
        .to_list(5000)
    )

    fs = get_fs()
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        await _write_dossiers(zf, responses, fs)

    buffer.seek(0)
    session_slug = _safe_name(session.get("name") or "session")
    parts = [session_slug]
    if formation:
        parts.append(_safe_name(formation))
    if normalized_mode == "online":
        parts.append("en-ligne")
    elif normalized_mode == "onsite":
        parts.append("presentiel")
    if normalized_status:
        parts.append(normalized_status)
    filename = f"dossiers_{'_'.join(parts)}_{datetime.utcnow().strftime('%Y%m%d')}.zip"

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
