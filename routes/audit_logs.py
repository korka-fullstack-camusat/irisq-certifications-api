from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from datetime import datetime
from bson import ObjectId
from database import get_database
from models.user import UserOut
from dependencies.auth import require_role

router = APIRouter()

ACTION_LABELS = {
    "session_created": "Session créée",
    "session_updated": "Session modifiée",
    "session_deleted": "Session supprimée",
    "response_status_updated": "Statut candidature modifié",
    "response_deleted": "Candidature supprimée",
    "documents_validation_updated": "Documents validés",
    "document_resubmit_requested": "Renvoi document demandé",
    "examiner_assigned": "Examinateur assigné",
    "final_evaluation_submitted": "Évaluation finale soumise",
    "exam_graded": "Examen noté",
    "evaluator_document_updated": "Document évaluateur mis à jour",
}


@router.get("", response_description="List audit logs (admin only)")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None, description="Filter by single action type"),
    actions: Optional[str] = Query(None, description="Filter by multiple action types (comma-separated)"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type: response | session"),
    date_from: Optional[str] = Query(None, description="ISO date from (e.g. 2025-01-01)"),
    date_to: Optional[str] = Query(None, description="ISO date to (e.g. 2025-12-31)"),
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()

    query: dict = {}
    if actions:
        action_list = [a.strip() for a in actions.split(",") if a.strip()]
        if action_list:
            query["action"] = {"$in": action_list}
    elif action:
        query["action"] = action
    if user_email:
        query["user_email"] = {"$regex": user_email, "$options": "i"}
    if resource_type:
        query["resource_type"] = resource_type
    if date_from or date_to:
        ts_filter: dict = {}
        if date_from:
            try:
                ts_filter["$gte"] = datetime.fromisoformat(date_from)
            except ValueError:
                pass
        if date_to:
            try:
                ts_filter["$lte"] = datetime.fromisoformat(date_to + "T23:59:59")
            except ValueError:
                pass
        if ts_filter:
            query["timestamp"] = ts_filter

    skip = (page - 1) * limit
    total = await db["audit_logs"].count_documents(query)
    logs = (
        await db["audit_logs"]
        .find(query)
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    for log in logs:
        log["_id"] = str(log["_id"])
        if isinstance(log.get("timestamp"), datetime):
            log["timestamp"] = log["timestamp"].isoformat()
        log["action_label"] = ACTION_LABELS.get(log.get("action", ""), log.get("action", ""))

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, -(-total // limit)),
        "logs": logs,
    }


@router.delete("/{log_id}", response_description="Delete an audit log entry (RH only)")
async def delete_audit_log(
    log_id: str,
    current_user: UserOut = Depends(require_role(["RH"])),
):
    db = get_database()
    if not ObjectId.is_valid(log_id):
        raise HTTPException(status_code=400, detail="Invalid log ID")
    result = await db["audit_logs"].delete_one({"_id": ObjectId(log_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return {"status": "deleted", "id": log_id}


@router.get("/actions", response_description="List available action types")
async def list_action_types(current_user: UserOut = Depends(require_role(["RH"]))):
    return [
        {"value": k, "label": v}
        for k, v in ACTION_LABELS.items()
    ]
