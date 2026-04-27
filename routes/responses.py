from fastapi import APIRouter, HTTPException, Body, Depends, BackgroundTasks, Query
from typing import List, Optional
import re
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
    notify_candidate_exam_unblocked,
)
from services.pdf_generator import generate_and_upload_candidate_pdf
from utils.audit import log_action

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
            "exam_appreciation": doc.get("exam_appreciation"),
            "assigned_examiner_email": doc.get("assigned_examiner_email"),
            "exam_answers": doc.get("exam_answers"),
            "answer_grades": doc.get("answer_grades"),
            "is_correction_locked": doc.get("is_correction_locked"),
            "exam_blocked": doc.get("exam_blocked"),
            "exam_blocked_reason": doc.get("exam_blocked_reason"),
            "exam_blocked_at": doc.get("exam_blocked_at"),
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

@router.get("/responses/check-email", response_description="Check if an email is eligible to apply across all active sessions")
async def check_email_eligibility(
    email: str = Query(..., description="Candidate email to verify"),
    certification: Optional[str] = Query(None, description="Certification name to check specifically"),
):
    """
    Public endpoint — called by the candidature form on email blur.

    If certification is provided:
    - Same certification already applied → blocked (ALREADY_APPLIED)
    - Different certification → eligible but warns (HAS_OTHER_APPLICATION)
    If omitted → warns with HAS_EXISTING_APPLICATION (informational, not blocking).
    """
    db = get_database()
    trimmed = email.strip().lower()
    if not trimmed:
        raise HTTPException(status_code=400, detail="Email is required")

    active_sessions = await db["sessions"].find({"status": "active"}, {"_id": 1}).to_list(200)
    active_ids = [str(s["_id"]) for s in active_sessions]

    if not active_ids:
        return {"eligible": True}

    existing_list = await db["responses"].find({
        "session_id": {"$in": active_ids},
        "email": {"$regex": f"^{re.escape(trimmed)}$", "$options": "i"},
    }).to_list(50)

    if not existing_list:
        return {"eligible": True}

    # Rejected → hard block regardless of certification
    rejected = next((e for e in existing_list if e.get("status") == "rejected"), None)
    if rejected:
        return {
            "eligible": False,
            "code": "APPLICATION_REJECTED",
            "message": "Votre candidature a été rejetée pour la session en cours. Veuillez attendre l'ouverture d'une nouvelle session.",
        }

    if certification:
        cert_norm = certification.strip()
        same_cert = [
            e for e in existing_list
            if (e.get("answers") or {}).get("Certification souhaitée", "").strip() == cert_norm
        ]
        other_cert = [
            e for e in existing_list
            if (e.get("answers") or {}).get("Certification souhaitée", "").strip() != cert_norm
        ]

        if same_cert:
            return {
                "eligible": False,
                "code": "ALREADY_APPLIED",
                "message": f"Vous avez déjà soumis une candidature pour « {cert_norm} » dans la session en cours.",
            }

        if other_cert:
            certs = list({
                (e.get("answers") or {}).get("Certification souhaitée", "Autre certification")
                for e in other_cert
            })
            return {
                "eligible": True,
                "code": "HAS_OTHER_APPLICATION",
                "existing_certifications": certs,
                "message": f"Vous avez déjà une candidature en cours pour : {', '.join(certs)}. Vous pouvez postuler à une autre certification.",
            }

    # No certification specified — warn without blocking
    certs = list({
        (e.get("answers") or {}).get("Certification souhaitée", "Autre certification")
        for e in existing_list
    })
    return {
        "eligible": True,
        "code": "HAS_EXISTING_APPLICATION",
        "existing_certifications": certs,
        "message": f"Vous avez déjà une candidature en cours ({', '.join(certs)}). Vous pouvez postuler à une autre certification.",
    }


@router.post("/forms/{form_id}/responses", response_description="Submit a response to a form", status_code=201)
async def create_response(form_id: str, response: ResponseCreate = Body(...), background_tasks: BackgroundTasks = BackgroundTasks()):
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
    if session_id and response_dict.get("email"):
        # Guard: same email + same session + same certification → duplicate.
        # Different certification in the same session is allowed.
        cert_name = (response_dict.get("answers") or {}).get("Certification souhaitée", "").strip()
        dup_query: dict = {
            "session_id": session_id,
            "email": {"$regex": f"^{re.escape(response_dict['email'].strip().lower())}$", "$options": "i"},
        }
        if cert_name:
            dup_query["answers.Certification souhaitée"] = cert_name

        existing = await db["responses"].find_one(dup_query)
        if existing:
            if existing.get("status") == "rejected":
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "APPLICATION_REJECTED",
                        "message": "Votre candidature a été rejetée pour cette certification dans cette session. Veuillez attendre l'ouverture d'une prochaine session.",
                    },
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ALREADY_APPLIED",
                    "message": f"Vous avez déjà postulé à « {cert_name or 'cette certification'} » pour la session en cours.",
                },
            )
    if session_id:
        if not ObjectId.is_valid(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID format")
        # If a public_id is already provided (2nd cert in a multi-certification submission),
        # don't increment the counter — the candidate already has their matricule.
        if response_dict.get("public_id"):
            session_doc = await db["sessions"].find_one({"_id": ObjectId(session_id)})
        else:
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

    candidate_id = response_dict.get("candidate_id", "N/A")
    candidate_name = response_dict.get("name", "Inconnu")
    candidate_email = response_dict.get("email")
    public_id = response_dict.get("public_id", "N/A")
    certification = response_dict.get("answers", {}).get("Certification souhaitée", "Non spécifiée")

    background_tasks.add_task(notify_rh_new_submission, candidate_id, candidate_name, certification)
    if candidate_email:
        background_tasks.add_task(
            notify_candidate_submission_received,
            candidate_email, candidate_name, public_id, certification, default_password,
        )

    return serialize_doc(created_response)


@router.get("/responses/multi-candidatures", response_description="Candidats ayant postulé à plusieurs formations dans la même session")
async def list_multi_candidatures(
    session_id: Optional[str] = Query(None, description="Filtrer par session"),
    current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"])),
):
    """
    Retourne les candidats ayant soumis plus d'une candidature pour des certifications
    différentes dans la même session.
    Chaque entrée groupe les dossiers complets par (email × session_id).
    """
    db = get_database()

    match_filter: dict = {}
    if session_id:
        if not ObjectId.is_valid(session_id):
            raise HTTPException(status_code=400, detail="ID de session invalide")
        match_filter["session_id"] = session_id

    # First: find (email × session_id) groups with count > 1
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": {"email": "$email", "session_id": "$session_id"},
            "count": {"$sum": 1},
            "response_ids": {"$push": {"$toString": "$_id"}},
            "name": {"$first": "$name"},
            "email": {"$first": "$email"},
            "session_id": {"$first": "$session_id"},
            "candidate_account_id": {"$first": "$candidate_account_id"},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"session_id": 1, "email": 1}},
    ]

    groups = await db["responses"].aggregate(pipeline).to_list(500)

    # Enrich with session names
    session_ids = list({g["session_id"] for g in groups if g.get("session_id")})
    sessions_map: dict = {}
    if session_ids:
        valid_ids = [sid for sid in session_ids if ObjectId.is_valid(sid)]
        async for s in db["sessions"].find({"_id": {"$in": [ObjectId(s) for s in valid_ids]}}):
            sessions_map[str(s["_id"])] = s.get("name", str(s["_id"]))

    # Fetch full dossier data for each group
    results = []
    for g in groups:
        ids = [ObjectId(rid) for rid in g["response_ids"] if ObjectId.is_valid(rid)]
        raw_dossiers = await db["responses"].find({"_id": {"$in": ids}}).sort("submitted_at", 1).to_list(20)

        dossiers_out = []
        for d in raw_dossiers:
            submitted = d.get("submitted_at")
            dossiers_out.append({
                "_id": str(d["_id"]),
                "public_id": d.get("public_id"),
                "form_id": d.get("form_id"),
                "status": d.get("status"),
                "exam_mode": d.get("exam_mode"),
                "exam_type": d.get("exam_type"),
                "exam_status": d.get("exam_status"),
                "exam_grade": d.get("exam_grade"),
                "final_grade": d.get("final_grade"),
                "final_appreciation": d.get("final_appreciation"),
                "submitted_at": submitted.isoformat() if isinstance(submitted, datetime) else submitted,
                "certification": (d.get("answers") or {}).get("Certification souhaitée", "N/A"),
                "answers": {
                    k: v for k, v in (d.get("answers") or {}).items()
                    if k in (
                        "Certification souhaitée", "Mode d'examen", "Type d'examen",
                        "CV", "Pièce d'identité", "Justificatif d'expérience", "Diplômes",
                        "Attestation de formation",
                    )
                },
                "documents_validation": d.get("documents_validation") or {},
            })

        results.append({
            "email": g["email"],
            "name": g["name"],
            "session_id": g["session_id"],
            "session_name": sessions_map.get(g["session_id"], g["session_id"]),
            "candidate_account_id": g.get("candidate_account_id"),
            "candidatures_count": g["count"],
            "dossiers": dossiers_out,
        })

    return results


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
async def update_response_status(id: str, status_update: StatusUpdate = Body(...), current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"])), background_tasks: BackgroundTasks = BackgroundTasks()):
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
            to_email = updated_response.get("email")
            pub_id = updated_response.get("public_id", "N/A")
            new_status = updated_response.get("status")
            certification = updated_response.get("answers", {}).get("Certification souhaitée", "Non spécifiée")
            if to_email:
                background_tasks.add_task(
                    notify_candidate_status_update,
                    to_email, pub_id, new_status, certification,
                    status_update.reason if status_update.status == "rejected" else None,
                )

            await log_action(
                action="response_status_updated",
                resource_type="response",
                resource_id=id,
                user_email=current_user.email,
                user_role=current_user.role,
                user_name=current_user.full_name,
                resource_label=updated_response.get("public_id", id),
                details={"new_status": status_update.status, "reason": status_update.reason},
            )

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

    await log_action(
        action="response_deleted",
        resource_type="response",
        resource_id=id,
        user_email=current_user.email,
        user_role=current_user.role,
        user_name=current_user.full_name,
        resource_label=response_doc.get("public_id", id),
        details={"name": response_doc.get("name"), "certification": response_doc.get("answers", {}).get("Certification souhaitée")},
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
        await log_action(
            action="evaluator_document_updated",
            resource_type="response",
            resource_id=id,
            user_email=current_user.email,
            user_role=current_user.role,
            user_name=current_user.full_name,
            resource_label=updated_response.get("public_id", id),
        )
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

    if response_in_db.get("is_correction_locked"):
        raise HTTPException(status_code=403, detail="Cette correction est verrouillée et ne peut plus être modifiée.")

    updates: dict = {
        "exam_status": grade_update.exam_status,
        "exam_comments": grade_update.exam_comments,
    }

    if grade_update.exam_appreciation is not None:
        updates["exam_appreciation"] = grade_update.exam_appreciation

    if grade_update.answer_grades:
        updates["answer_grades"] = grade_update.answer_grades
        if grade_update.exam_grade:
            updates["exam_grade"] = grade_update.exam_grade
        else:
            # Auto-calculate total from per-question grades
            total_earned = sum(float(g.get("points_earned", 0)) for g in grade_update.answer_grades)
            total_max = sum(float(g.get("max_points", 0)) for g in grade_update.answer_grades)
            if total_max > 0:
                updates["exam_grade"] = f"{total_earned:.2g}/{total_max:.2g}"
            else:
                updates["exam_grade"] = str(total_earned)
    elif grade_update.exam_grade:
        updates["exam_grade"] = grade_update.exam_grade

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": updates}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one({"_id": ObjectId(id)})
        await log_action(
            action="exam_graded",
            resource_type="response",
            resource_id=id,
            user_email=current_user.email,
            user_role=current_user.role,
            user_name=current_user.full_name,
            resource_label=updated_response.get("public_id", id),
            details={"exam_grade": grade_update.exam_grade, "exam_status": grade_update.exam_status},
        )
        return serialize_doc(updated_response, user_role=current_user.role)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")


@router.post("/responses/{id}/lock-correction", response_description="Verrouiller définitivement la correction d'une copie")
async def lock_correction(id: str, current_user: UserOut = Depends(require_role(["CORRECTEUR"]))):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    response_in_db = await db["responses"].find_one({"_id": ObjectId(id)})
    if not response_in_db:
        raise HTTPException(status_code=404, detail=f"Response {id} not found")

    if response_in_db.get("assigned_examiner_email") != current_user.email:
        raise HTTPException(status_code=403, detail="Not assigned to this exam")

    if response_in_db.get("is_correction_locked"):
        raise HTTPException(status_code=409, detail="Cette correction est déjà verrouillée.")

    if not response_in_db.get("exam_grade"):
        raise HTTPException(status_code=400, detail="Vous devez d'abord enregistrer une note avant de verrouiller.")

    updated = await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {"is_correction_locked": True, "correction_locked_at": datetime.utcnow()}}
    )

    if updated.matched_count == 1:
        updated_response = await db["responses"].find_one({"_id": ObjectId(id)})
        await log_action(
            action="correction_locked",
            resource_type="response",
            resource_id=id,
            user_email=current_user.email,
            user_role=current_user.role,
            user_name=current_user.full_name,
            resource_label=updated_response.get("public_id", id),
        )
        return serialize_doc(updated_response, user_role=current_user.role)

    raise HTTPException(status_code=404, detail=f"Response {id} not found")


@router.post("/responses/{id}/unblock-exam", response_description="Débloquer l'accès à l'examen d'un candidat bloqué")
async def unblock_exam(
    id: str,
    background_tasks: BackgroundTasks,
    current_user: UserOut = Depends(require_role(["EVALUATEUR", "RH"])),
):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid response ID format")

    response_in_db = await db["responses"].find_one({"_id": ObjectId(id)})
    if not response_in_db:
        raise HTTPException(status_code=404, detail=f"Response {id} not found")

    await db["responses"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "exam_blocked": False,
            "exam_blocked_reason": None,
            "exam_blocked_at": None,
            "exam_unblocked_by": current_user.email,
            "exam_unblocked_at": datetime.utcnow(),
        }},
    )
    updated_response = await db["responses"].find_one({"_id": ObjectId(id)})
    await log_action(
        action="exam_unblocked",
        resource_type="response",
        resource_id=id,
        user_email=current_user.email,
        user_role=current_user.role,
        user_name=current_user.full_name,
        resource_label=updated_response.get("public_id", id),
    )

    # Notifier le candidat par email
    candidate_email = updated_response.get("email")
    if candidate_email:
        certification = (updated_response.get("answers") or {}).get("Certification souhaitée", "")
        background_tasks.add_task(
            notify_candidate_exam_unblocked,
            candidate_email,
            updated_response.get("name") or "Candidat",
            updated_response.get("public_id") or "",
            certification,
        )

    return serialize_doc(updated_response, user_role=current_user.role)


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
async def assign_examiner(id: str, assignment: AssignExaminerUpdate = Body(...), current_user: UserOut = Depends(require_role(["EVALUATEUR", "RH"])), background_tasks: BackgroundTasks = BackgroundTasks()):
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

        # Send the email notification in the background so the response returns immediately
        if assignment.examiner_email:
            background_tasks.add_task(
                notify_examiner_assignment,
                to_email=assignment.examiner_email,
                candidate_id=candidate_id,
                certification=certification_name,
            )

        await log_action(
            action="examiner_assigned",
            resource_type="response",
            resource_id=id,
            user_email=current_user.email,
            user_role=current_user.role,
            user_name=current_user.full_name,
            resource_label=updated_response.get("public_id", id),
            details={"examiner_email": assignment.examiner_email, "certification": certification_name},
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
        await log_action(
            action="final_evaluation_submitted",
            resource_type="response",
            resource_id=id,
            user_email=current_user.email,
            user_role=current_user.role,
            user_name=current_user.full_name,
            resource_label=updated_response.get("public_id", id),
            details={"final_grade": evaluation.final_grade, "final_appreciation": evaluation.final_appreciation},
        )
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
    await log_action(
        action="documents_validation_updated",
        resource_type="response",
        resource_id=id,
        user_email=current_user.email,
        user_role=current_user.role,
        user_name=current_user.full_name,
        resource_label=updated_response.get("public_id", id),
    )
    return serialize_doc(updated_response, user_role=current_user.role)


@router.post("/responses/{id}/request-document-resubmit", response_description="Ask the candidate by email to re-upload a specific document")
async def request_document_resubmit(
    id: str,
    payload: DocumentResubmitRequest = Body(...),
    current_user: UserOut = Depends(require_role(["RH"])),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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

    # Fire the email in the background — response returns immediately
    background_tasks.add_task(
        notify_candidate_document_issue,
        to_email=to_email,
        candidate_name=response_doc.get("name", "Candidat"),
        public_id=response_doc.get("public_id", "N/A"),
        certification=response_doc.get("answers", {}).get("Certification souhaitée", "Non spécifiée"),
        document_name=payload.document_name,
        message=payload.message or "",
    )

    await log_action(
        action="document_resubmit_requested",
        resource_type="response",
        resource_id=id,
        user_email=current_user.email,
        user_role=current_user.role,
        user_name=current_user.full_name,
        resource_label=response_doc.get("public_id", id),
        details={"document_name": payload.document_name, "message": payload.message},
    )

    return {"status": "email_sent", "document_name": payload.document_name}
