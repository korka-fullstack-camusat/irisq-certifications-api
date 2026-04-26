import asyncio
import logging
import os
import secrets
import traceback
from datetime import datetime
from typing import List

from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from database import ensure_fs

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
    "application/msword",  # DOC
}

MAX_FILE_SIZE = 15 * 1024 * 1024   # 15 MB par fichier
MAX_RETRY     = 3                  # tentatives GridFS
RETRY_DELAY   = 1.0                # secondes entre tentatives


async def _upload_one(fs, content: bytes, filename: str, content_type: str) -> str:
    """Upload un fichier dans GridFS avec retry automatique."""
    ext = os.path.splitext(filename)[1]
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(6)}{ext}"

    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(1, MAX_RETRY + 1):
        try:
            file_id = await fs.upload_from_stream(
                unique_name,
                content,
                metadata={"content_type": content_type, "original_name": filename},
            )
            return f"/api/files/{str(file_id)}"
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "GridFS upload attempt %d/%d failed for '%s': %s",
                attempt, MAX_RETRY, filename, exc,
            )
            if attempt < MAX_RETRY:
                # Renouveler le bucket au cas où la connexion est cassée
                fs = await ensure_fs(force_reconnect=True)
                await asyncio.sleep(RETRY_DELAY * attempt)

    logger.error(
        "GridFS upload definitively failed for '%s': %s\n%s",
        filename, last_exc, traceback.format_exc(),
    )
    raise last_exc


@router.post("/upload", response_description="Upload multiple files")
async def upload_files(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier reçu.")

    uploaded_files = []

    for file in files:
        # ── Vérification type MIME ─────────────────────────────────────────
        content_type = (file.content_type or "").lower().strip()
        if content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Type de fichier non autorisé : {file.filename} ({content_type}). "
                       f"Formats acceptés : PDF, JPEG, PNG, WEBP, DOCX.",
            )

        # ── Lecture + vérification taille ─────────────────────────────────
        try:
            content = await file.read()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Impossible de lire le fichier {file.filename}: {exc}")

        if len(content) == 0:
            raise HTTPException(status_code=400, detail=f"Le fichier {file.filename} est vide.")

        if len(content) > MAX_FILE_SIZE:
            mb = len(content) / (1024 * 1024)
            raise HTTPException(
                status_code=400,
                detail=f"Le fichier {file.filename} est trop volumineux ({mb:.1f} MB). Maximum : 15 MB.",
            )

        # ── Upload GridFS avec retry ───────────────────────────────────────
        try:
            fs = await ensure_fs()
            file_url = await _upload_one(fs, content, file.filename or "file", content_type)
            uploaded_files.append({
                "original_name": file.filename,
                "file_url": file_url,
                "content_type": content_type,
            })
            logger.info("Uploaded '%s' → %s", file.filename, file_url)
        except Exception as exc:
            logger.error("Upload failed for '%s': %s", file.filename, exc)
            raise HTTPException(
                status_code=500,
                detail=f"Erreur lors de l'enregistrement de {file.filename}. Veuillez réessayer.",
            )

    return {
        "message": "Fichiers uploadés avec succès",
        "files": uploaded_files,
        # Alias pour compatibilité frontend
        "file_urls": [f["file_url"] for f in uploaded_files],
    }


@router.get("/files/{file_id}", response_description="Get a file by ID")
async def get_file(file_id: str):
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=400, detail="ID de fichier invalide.")
    try:
        fs = await ensure_fs()
        grid_out  = await fs.open_download_stream(ObjectId(file_id))
        content   = await grid_out.read()
        content_type = "application/octet-stream"
        if grid_out.metadata and "content_type" in grid_out.metadata:
            content_type = grid_out.metadata["content_type"]
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Length": str(len(content)), "Accept-Ranges": "bytes"},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")


@router.head("/files/{file_id}", response_description="Probe file metadata")
async def head_file(file_id: str):
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=400, detail="ID de fichier invalide.")
    try:
        fs = await ensure_fs()
        grid_out = await fs.open_download_stream(ObjectId(file_id))
        content_type = "application/octet-stream"
        if grid_out.metadata and "content_type" in grid_out.metadata:
            content_type = grid_out.metadata["content_type"]
        return Response(
            status_code=200,
            media_type=content_type,
            headers={"Content-Length": str(grid_out.length or 0), "Accept-Ranges": "bytes"},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
