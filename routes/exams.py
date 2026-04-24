from fastapi import APIRouter, HTTPException, Body, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import List, Optional
from database import get_database, get_fs
from models.exam import ExamCreate
from models.user import UserOut
from dependencies.auth import require_role
from bson import ObjectId
from datetime import datetime
from email_service import notify_candidate_exam_link
import os
import secrets
import urllib.parse
import traceback
from services.parser_service import parse_exam_document

router = APIRouter()

def serialize_doc(doc):
    """Recursively convert ObjectId and datetime for JSON serialization."""
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, list):
                result[key] = [serialize_doc(item) for item in value]
            elif isinstance(value, dict):
                result[key] = serialize_doc(value)
            else:
                result[key] = value
        return result
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    return doc

@router.post("/exams", response_description="Create a new exam", status_code=201)
async def create_exam(exam: ExamCreate = Body(...), current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"]))):
    db = get_database()
    
    try:
        exam_dict = exam.model_dump()
        exam_dict["created_at"] = datetime.utcnow()
        exam_dict["created_by"] = current_user.email
        
        # ── Parse the uploaded document into interactive questions ──
        doc_url = exam_dict.get("document_url", "")
        exam_dict["parsed_questions"] = []
        
        if doc_url and "/api/files/" in doc_url:
            try:
                # Extract the File ID from the GridFS URL
                file_id_str = doc_url.split("/api/files/")[-1]
                if ObjectId.is_valid(file_id_str):
                    fs = get_fs()
                    grid_out = await fs.open_download_stream(ObjectId(file_id_str))
                    content = await grid_out.read()
                    
                    # Determine original extension if possible or default to pdf
                    ext = ".pdf"
                    if grid_out.metadata and "original_name" in grid_out.metadata:
                        ext = os.path.splitext(grid_out.metadata["original_name"])[1]
                        
                    import tempfile
                    # Save temporarily to disk so docx/pdfplumber can read it
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
                        temp_file.write(content)
                        temp_path = temp_file.name
                        
                    try:
                        questions = parse_exam_document(temp_path)
                        exam_dict["parsed_questions"] = questions
                    except Exception as parse_e:
                        print(f"Failed to parse document content: {parse_e}")
                    finally:
                        # Clean up the temp file
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                            
            except Exception as e:
                print(f"Failed to retrieve and parse exam document from GridFS: {e}")
                
        new_exam = await db["exams"].insert_one(exam_dict)
        created_exam = await db["exams"].find_one({"_id": new_exam.inserted_id})
        return JSONResponse(status_code=201, content=serialize_doc(created_exam))
    except Exception as e:
        print(f"Error creating exam: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create exam: {str(e)}")

@router.get("/exams", response_description="List all exams")
async def list_exams(certification: Optional[str] = None):
    db = get_database()
    query = {}
    if certification:
        query["certification"] = certification
        
    exams = await db["exams"].find(query).sort("created_at", -1).to_list(1000)
    return [serialize_doc(e) for e in exams]

@router.delete("/exams/{id}", response_description="Delete an exam")
async def delete_exam(id: str, current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"]))):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid exam ID format")
        
    deleted = await db["exams"].delete_one({"_id": ObjectId(id)})
    if deleted.deleted_count == 1:
        return {"message": "Exam deleted successfully"}
        
    raise HTTPException(status_code=404, detail=f"Exam {id} not found")

@router.post("/exams/{id}/publish", response_description="Publish an exam and notify approved candidates")
async def publish_exam(
    id: str,
    background_tasks: BackgroundTasks,
    current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"])),
):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid exam ID format")

    exam = await db["exams"].find_one({"_id": ObjectId(id)})
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam {id} not found")

    certification_name = exam.get("certification")
    if not certification_name:
        raise HTTPException(status_code=400, detail="Exam has no certification type")

    # Find all approved responses for this certification
    approved_responses = await db["responses"].find({
        "status": "approved",
        "answers.Certification souhaitée": certification_name
    }).to_list(1000)

    notified_count = 0
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    for response in approved_responses:
        candidate_email = response.get("email")
        public_id = response.get("public_id", "N/A")

        first_name = response.get("answers", {}).get("Prénom", "")
        last_name = response.get("answers", {}).get("Nom", "Candidat")
        full_name = f"{first_name} {last_name}".strip()

        exam_token = response.get("exam_token")
        if not exam_token:
            exam_token = secrets.token_urlsafe(32)
            await db["responses"].update_one(
                {"_id": response["_id"]},
                {"$set": {"exam_token": exam_token}}
            )

        exam_link = f"{frontend_url}/examen/{exam_token}"

        if candidate_email:
            # Queue each email as a background task — the loop returns immediately
            background_tasks.add_task(
                notify_candidate_exam_link,
                to_email=candidate_email,
                public_id=public_id,
                candidate_name=full_name,
                certification=certification_name,
                exam_link=exam_link,
            )
            notified_count += 1

    return {
        "message": "Exam published successfully",
        "notified_candidates_count": notified_count
    }
