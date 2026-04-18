from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from typing import List
from database import get_fs
from bson import ObjectId
import os
import secrets
from datetime import datetime

router = APIRouter()

@router.post("/upload", response_description="Upload multiple files")
async def upload_files(files: List[UploadFile] = File(...)):
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # DOCX
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    uploaded_files = []
    fs = get_fs()
    
    for file in files:
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"File type not permitted for {file.filename}")

        try:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File {file.filename} is too large. Max size is 10MB.")

            original_ext = os.path.splitext(file.filename)[1]
            unique_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}{original_ext}"
            
            # Upload to GridFS
            file_id = await fs.upload_from_stream(
                unique_filename,
                content,
                metadata={"content_type": file.content_type, "original_name": file.filename}
            )
            
            uploaded_files.append({
                "original_name": file.filename,
                "file_url": f"/api/files/{str(file_id)}",
                "content_type": file.content_type
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {str(e)}")
            
    return {"message": "Files uploaded successfully", "files": uploaded_files}

@router.get("/files/{file_id}", response_description="Get a file by ID")
async def get_file(file_id: str):
    fs = get_fs()
    try:
        if not ObjectId.is_valid(file_id):
            raise HTTPException(status_code=400, detail="Invalid file ID")

        grid_out = await fs.open_download_stream(ObjectId(file_id))
        content = await grid_out.read()

        content_type = "application/octet-stream"
        if grid_out.metadata and "content_type" in grid_out.metadata:
            content_type = grid_out.metadata["content_type"]

        headers = {
            "Content-Length": str(len(content)),
            "Accept-Ranges": "bytes",
        }
        return Response(content=content, media_type=content_type, headers=headers)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")


@router.head("/files/{file_id}", response_description="Probe file metadata")
async def head_file(file_id: str):
    """Lightweight HEAD handler so clients (e.g. the inline preview modal)
    can determine the file's Content-Type without fetching the full payload."""
    fs = get_fs()
    try:
        if not ObjectId.is_valid(file_id):
            raise HTTPException(status_code=400, detail="Invalid file ID")

        grid_out = await fs.open_download_stream(ObjectId(file_id))

        content_type = "application/octet-stream"
        if grid_out.metadata and "content_type" in grid_out.metadata:
            content_type = grid_out.metadata["content_type"]

        headers = {
            "Content-Length": str(grid_out.length or 0),
            "Accept-Ranges": "bytes",
        }
        return Response(status_code=200, media_type=content_type, headers=headers)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
