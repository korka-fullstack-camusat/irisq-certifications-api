from fastapi import APIRouter, HTTPException, Body, Depends
from typing import List, Optional
from database import get_database
from models.response import (
    ResponseCreate, StatusUpdate, EvaluatorDocUpdate, ExamSubmissionUpdate,
    AntiCheatUpdate, AssignExaminerUpdate, FinalEvaluationUpdate,
    DocumentsValidationUpdate, DocumentResubmitRequest
)
from models.user import UserOut
from dependencies.auth import get_current_user, require_role, get_current_user_optional
from bson import ObjectId
from pymongo import ReturnDocument
from datetime import datetime
import secrets
from utils.security import get_password_hash
from email_service import (
    notify_rh_new_submission,
    notify_candidate_status_update,
    notify_examiner_assignment,
    notify_candidate_submission_received,
    notify_candidate_document_issue,
)
from services.pdf_generator import generate_and_upload_candidate_pdf

router = APIRouter()

def serialize_doc(doc, user_role: Optional[str] = None):
    doc["_id"] = str(doc["_id"])

    if user_role == "CORRECTEUR":
        cert_name = doc.get("answers", {}).get("Certification souhaitée", "Non spécifiée")
        return {
            "_id": doc["_id"],
            "public_id": doc.get("public_id"),
            "candidate_id": doc.get("candidate_id"),
            "status": doc.get("status"),
            "submitted_at": doc.get("submitted_at"),
            "exam_document": doc.get("exam_document"),
            "exam_grade": doc.get("exam_grade"),
            "exam_status": doc.get("exam_status"),
            "exam_comments": doc.get("exam_comments"),
            "assigned_examiner_email": doc.get("assigned_examiner_email"),
            "answers": {
                "Certification souhaitée": cert_name
            }
        }

    # PII Filtering for non-RH users
    if user_role and user_role != "RH":
        # Keep public_id, candidate_id, form_id, status, etc., but remove direct PII
        doc.pop("name", None)
        doc.pop("email", None)
        doc.pop("phone", None)

        # Filter answers payload which often contains PII
        if "answers" in doc:
            safe_answers = {}
            # Allow safe fields to pass through (like Certification, CV urls maybe)
            for key, val in doc["answers"].items():
                lower_key = key.lower()
                if "nom" in lower_key or "email" in lower_key or "téléphone" in lower_key or "adresse" in lower_key or "naissance" in lower_key:
                    safe_answers[key] = "[Masqué pour confidentialité]"
                else:
                    safe_answers[key] = val
            doc["answers"] = safe_answers

    return doc

@router.post("/forms/{form_id}/responses", response_description="Submit a response to a form", status_code=201)
async def create_response(form_id: str, response: ResponseCreate = Body(...)):
    db = get_database()

    # Check if form exists
    if not ObjectId.is_valid(form_id):
        raise HTTPException(status_code=400, detail="Invalid form ID format")

    form = await db["forms"].find_one({"_id": ObjectId(form_id)})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    response_dict = response.model_dump()
    response_dict["form_id"] = form_id
    now = datetime.utcnow()
    response_dict["submitted_at"] = now
    response_dict["candidate_id"] = response_dict.get("candidate_id") or f"CAND-{secrets.token_hex(3).upper()}"
    response_dict["exam_token"] = secrets.token_urlsafe(32)  # Cryptographically secure exam token

    # Validate session_id (if provided) exists and atomically allocate candidate sequence
    session_id = response_dict.get("session_id")
    session_seq = 0
    candidate_seq = 0
    if session_id:
        if not ObjectId.is_valid(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID format")
        session_doc = await db["sessions"].find_one_and_update(
            {"_id": ObjectId(session_id)},
            {"$inc": {"candidate_counter": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if not session_doc:
            raise HTTPException(status_code=404, detail="Session not found")
        session_seq = session_doc.get("sequence_number") or 1
        candidate_seq = session_doc.get("candidate_counter") or 1

    # Codification: IC{YY}D{SEQ:02d}{MODE}-{CAND:04d} (ex: IC24D01L-0001 / IC24D01P-0001)
    # MODE suffix encodes the exam mode chosen by the candidate:
    #   L = En ligne (online) — P = Présentiel (onsite) — omitted if unspecified.
    exam_mode = (response_dict.get("exam_mode") or "").strip().lower()
    mode_letter = "L" if exam_mode == "online" else "P" if exam_mode == "onsite" else ""

    if not response_dict.get("public_id"):
        if session_seq and candidate_seq:
            year_suffix = now.strftime("%y")
            response_dict["public_id"] = (
                f"IC{year_suffix}D{session_seq:02d}{mode_letter}-{candidate_seq:04d}"
            )
        else:
            # Fallback (response not attached to a session)
            response_dict["public_id"] = (
                f"IC{now.strftime('%y')}D00{mode_letter}-{secrets.token_hex(2).upper()}"
            )

    # Default password for the candidate portal (public_id acts as the username).
    # 8 URL-safe chars — simple to type, communicated once by email.
    default_password = secrets.token_urlsafe(6)[:8]
    response_dict["password_hash"] = get_password_hash(default_password)
    response_dict["must_change_password"] = True

    new_response = await db["responses"].insert_one(response_dict)

    # Update form response count
    await db["forms"].update_one(
        {"_id": ObjectId(form_id)},
        {"$inc": {"responses_count": 1}, "$set": {"updated_at": datetime.utcnow()}}
    )

    created_response = await db["responses"].find_one({"_id": new_response.inserted_id})

    # Send email notifications
    try:
        candidate_id = response_dict.get("candidate_id", "N/A")
        candidate_name = response_dict.get("name", "Inconnu")
        candidate_email = response_dict.get("email")
        public_id = response_dict.get("public_id", "N/A")
        certification = response_dict.get("answers", {}).get("Certification souhaitée", "Non spécifiée")

        # Notify HR
        notify_rh_new_submission(candidate_id, candidate_name, certification)

        # Notify Candidate
        if candidate_email:
            notify_candidate_submission_received(
                candidate_email, candidate_name, public_id, certification, default_password
            )

    except Exception as e:
        print(f"[EMAIL] Notification failed but submission saved: {e}")

    return serialize_doc(created_response)

@router.get("/forms/{form_id}/responses", response_description="Get all responses for a form")
async def list_responses(form_id: str, current_user: UserOut = Depends(get_current_user)):
    db = get_database()
    if not ObjectId.is_valid(form_id):
        raise HTTPException(status_code=400, detail="Invalid form ID format")

    query = {"form_id": form_id}
    if current_user.role == "CORRECTEUR":
        # Ensure regex case-insensitive match just to be safe
        query["assigned_examiner_email"] = {"$regex": f"^{current_user.email}$", "$options": "i"}

    responses = await db["responses"].find(query).to_list(1000)
    return [serialize_doc(r, user_role=current_user.role) for r in responses]

@router.get("/responses/{id}", response_description="Get a single response by ID")
async def get_response(id: str, current_user: Optional[UserOut] = Depends(get_current_user_optional)):
    db = get_database()

    if ObjectId.is_valid(id):
        query = {"_id": ObjectId(id)}
    else:
        query = {"exam_token": id}

    response = await db["responses"].find_one(query)
    if not response:
        raise HTTPException(status_code=404, detail=f"Response {id} not found")

    user_role = current_user.role if current_user else None
    return serialize_doc(response, user_role=user_role)

@router.patch("/responses/{id}/status", response_description="Update response status")
async def update_response_status(id: str, status_update: StatusUpdate = Body(...), current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"]))):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    updates: dict = {"status": status_update.status}
    # Rejection blocks the candidate portal credentials; approval/re-opening unblocks them.
    if status_update.status == "rejected":
        updates["credentials_blocked"] = True
        updates["credentials_blocked_at"] = datetime.utcnow()
        if status_update.reason:
            updates["rejection_reason"] = status_update.reason
    else:
        updates["credentials_blocked"] = False

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": updates}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one({"_id": ObjectId(id)})

        # Notify Candidate ONLY if status was actually modified
        if updated.modified_count == 1:
            try:
                to_email = updated_response.get("email")
                public_id = updated_response.get("public_id", "N/A")
                status = updated_response.get("status")
                certification = updated_response.get("answers", {}).get("Certification souhaitée", "Non spécifiée")

                if to_email:
                    notify_candidate_status_update(
                        to_email, public_id, status, certification,
                        reason=status_update.reason if status_update.status == "rejected" else None,
                    )
            except Exception as e:
                print(f"[EMAIL] Candidate notification failed: {e}")

        return serialize_doc(updated_response, user_role=current_user.role)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")

@router.delete("/responses/{id}", response_description="Delete a rejected candidature (RH only)")
async def delete_response(id: str, current_user: UserOut = Depends(require_role(["RH"]))):
    """Hard-delete a candidature. Only allowed when the dossier has been
    explicitly rejected — prevents accidental loss of in-flight applications.
    """
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    response_doc = await db["responses"].find_one({"_id": ObjectId(id)})
    if not response_doc:
        raise HTTPException(status_code=404, detail=f"Response {id} not found")

    if response_doc.get("status") != "rejected":
        raise HTTPException(
            status_code=409,
            detail="Seules les candidatures rejetées peuvent être supprimées.",
        )

    await db["responses"].delete_one({"_id": ObjectId(id)})

    # Keep the form's response counter in sync so the dashboard stays accurate.
    form_id = response_doc.get("form_id")
    if form_id and ObjectId.is_valid(form_id):
        await db["forms"].update_one(
            {"_id": ObjectId(form_id)},
            {"$inc": {"responses_count": -1}, "$set": {"updated_at": datetime.utcnow()}},
        )

    return {"status": "deleted", "id": id}


@router.patch("/responses/{id}/evaluate", response_description="Update evaluator document")
async def update_evaluator_document(id: str, doc_update: EvaluatorDocUpdate = Body(...), current_user: UserOut = Depends(require_role(["EVALUATEUR"]))):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {"evaluator_document": doc_update.evaluator_document}}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one({"_id": ObjectId(id)})
        return serialize_doc(updated_response, user_role=current_user.role)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")

@router.patch("/responses/{id}/grade", response_description="Submit exam grade by correcteur")
async def update_exam_grade(id: str, grade_update: ExamSubmissionUpdate = Body(...), current_user: UserOut = Depends(require_role(["CORRECTEUR"]))):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    # Check if the exam is assigned to this corrector
    response_in_db = await db["responses"].find_one({"_id": ObjectId(id)})
    if not response_in_db:
        raise HTTPException(status_code=404, detail=f"Response {id} not found")

    if response_in_db.get("assigned_examiner_email") != current_user.email:
        raise HTTPException(status_code=403, detail="Not assigned to this exam")

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "exam_grade": grade_update.exam_grade,
            "exam_status": grade_update.exam_status,
            "exam_comments": grade_update.exam_comments
        }}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one({"_id": ObjectId(id)})
        return serialize_doc(updated_response, user_role=current_user.role)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")

@router.patch("/responses/{id}/anti-cheat", response_description="Submit technical exam with anti-cheat report")
async def submit_exam_with_anticheat(id: str, submission: AntiCheatUpdate = Body(...)):
    db = get_database()

    if ObjectId.is_valid(id):
        query = {"_id": ObjectId(id)}
    else:
        query = {"exam_token": id}

    response_doc = await db["responses"].find_one(query)
    if not response_doc:
         raise HTTPException(status_code=404, detail=f"Response {id} not found")

    # Generate the PDF document from the answers
    generated_pdf_url = submission.exam_document

    try:
        # We need the candidate's chosen certification from their answers
        certification_name = response_doc.get("answers", {}).get("Certification souhaitée", "Non spécifiée")

        candidate_info = {
            "candidate_id": response_doc.get("candidate_id", f"CAND-{str(response_doc['_id'])[-6:].upper()}"),
            "certification": certification_name
        }

        # We need the exam to get the original questions.
        # The exam was created for this certification.
        exam = await db["exams"].find_one({"certification": certification_name}, sort=[("created_at", -1)])
        questions = exam.get("parsed_questions", []) if exam else []

        if submission.exam_answers or submission.cheat_alerts:
            pdf_url = await generate_and_upload_candidate_pdf(
                candidate_info=candidate_info,
                questions=questions,
                answers=submission.exam_answers or [],
                cheat_alerts=submission.cheat_alerts or []
            )
            if pdf_url:
                generated_pdf_url = pdf_url
    except Exception as e:
        print(f"Failed to generate candidate PDF: {e}")

    updated = await db["responses"].update_one(
        query,
        {"$set": {
            "exam_document": generated_pdf_url,
            "cheat_alerts": submission.cheat_alerts,
            "exam_answers": submission.exam_answers,
            "candidate_photos": submission.candidate_photos,
        }}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one(query)
        return serialize_doc(updated_response)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")

@router.patch("/responses/{id}/assign", response_description="Assign an exam to an examiner")
async def assign_examiner(id: str, assignment: AssignExaminerUpdate = Body(...), current_user: UserOut = Depends(require_role(["EVALUATEUR", "RH"]))):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "assigned_examiner_email": assignment.examiner_email,
        }}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one({"_id": ObjectId(id)})

        # Determine the candidate ID and certification name for the email
        candidate_id = updated_response.get("candidate_id", f"CAND-{str(updated_response['_id'])[-6:].upper()}")

        # Fetch the form to get the certification name
        form_id = updated_response.get("form_id")
        certification_name = "Certification Inconnue"
        if form_id:
            form = await db["forms"].find_one({"_id": ObjectId(form_id)})
            if form:
                certification_name = form.get("title", certification_name)

        # Send the email notification
        if assignment.examiner_email:
            notify_examiner_assignment(
                to_email=assignment.examiner_email,
                candidate_id=candidate_id,
                certification=certification_name
            )

        return serialize_doc(updated_response, user_role=current_user.role)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")

@router.patch("/responses/{id}/final-evaluation", response_description="Submit evaluator's final evaluation")
async def evaluate_final_response(id: str, evaluation: FinalEvaluationUpdate = Body(...), current_user: UserOut = Depends(require_role(["EVALUATEUR"]))):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "final_grade": evaluation.final_grade,
            "final_appreciation": evaluation.final_appreciation,
            "status": "evaluated"   # Change the actual candidate status
        }}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one({"_id": ObjectId(id)})
        return serialize_doc(updated_response, user_role=current_user.role)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")


# ──────────────────────────────────────────────────────────────
# Document validation & candidate resubmit request (Admin / RH)
# ──────────────────────────────────────────────────────────────

@router.patch("/responses/{id}/documents-validation", response_description="Update the per-document validation checklist")
async def update_documents_validation(
    id: str,
    payload: DocumentsValidationUpdate = Body(...),
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {"documents_validation": payload.documents_validation}}
    )

    if updated.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Response {id} not found")

    updated_response = await db["responses"].find_one({"_id": ObjectId(id)})
    return serialize_doc(updated_response, user_role=current_user.role)


@router.post("/responses/{id}/request-document-resubmit", response_description="Ask the candidate by email to re-upload a specific document")
async def request_document_resubmit(
    id: str,
    payload: DocumentResubmitRequest = Body(...),
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    response_doc = await db["responses"].find_one({"_id": ObjectId(id)})
    if not response_doc:
        raise HTTPException(status_code=404, detail=f"Response {id} not found")

    to_email = response_doc.get("email")
    if not to_email:
        raise HTTPException(status_code=400, detail="Candidate has no email on file")

    try:
        notify_candidate_document_issue(
            to_email=to_email,
            candidate_name=response_doc.get("name", "Candidat"),
            public_id=response_doc.get("public_id", "N/A"),
            certification=response_doc.get("answers", {}).get("Certification souhaitée", "Non spécifiée"),
            document_name=payload.document_name,
            message=payload.message or "",
        )
    except Exception as e:
        print(f"[EMAIL] Document issue notification failed: {e}")
        raise HTTPException(status_code=500, detail="Email notification failed")

    # Track that we asked the candidate to resubmit this specific document
    current_validation = response_doc.get("documents_validation", {}) or {}
    current_validation[payload.document_name] = {
        **(current_validation.get(payload.document_name) or {}),
        "valid": False,
        "resubmit_requested": True,
        "resubmit_requested_at": datetime.utcnow().isoformat(),
        "resubmit_message": payload.message or "",
    }
    await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {"documents_validation": current_validation}}
    )

    return {"status": "email_sent", "document_name": payload.document_name}
