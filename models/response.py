from pydantic import BaseModel, Field, EmailStr
from typing import Dict, Any, List, Optional
from datetime import datetime


class ResponseBase(BaseModel):
    form_id: str
    session_id: Optional[str] = None  # New: session this candidature belongs to
    name: str
    email: EmailStr
    profile: str
    answers: Dict[str, Any]
    score: Optional[str] = None
    status: str = "pending"  # pending, approved, rejected
    candidate_id: Optional[str] = None
    public_id: Optional[str] = None
    exam_token: Optional[str] = None
    evaluator_document: Optional[str] = None

    # Correcteur fields
    exam_document: Optional[str] = None
    exam_grade: Optional[str] = None
    exam_status: Optional[str] = None
    exam_comments: Optional[str] = None

    # Evaluator Final Decision
    final_grade: Optional[str] = None
    final_appreciation: Optional[str] = None

    # Anti-Cheat & Submissions
    cheat_alerts: Optional[list[str]] = None
    exam_answers: Optional[list[Dict[str, Any]]] = None
    assigned_examiner_email: Optional[str] = None
    candidate_photos: Optional[list[str]] = None

    # Per-question grading: [{question_id, points_earned, max_points, comment}]
    answer_grades: Optional[List[Dict[str, Any]]] = None
    is_correction_locked: Optional[bool] = None
    correction_locked_at: Optional[datetime] = None

    # Blocage d'examen (rechargement de page, triche avérée, etc.)
    exam_blocked: Optional[bool] = None
    exam_blocked_reason: Optional[str] = None
    exam_blocked_at: Optional[datetime] = None

    # Document validation checklist
    # Shape: { "<document_key>": { "valid": true|false, "notes": "..." } }
    documents_validation: Optional[Dict[str, Any]] = None

    # Exam logistics chosen at application time.
    # exam_mode : "online" | "onsite"              (En ligne / Présentiel)
    # exam_type : "direct" | "after_formation"     (Examen direct / Examen après formation IRISQ)
    exam_mode: Optional[str] = None
    exam_type: Optional[str] = None


class ResponseCreate(ResponseBase):
    pass


class ResponseDBModel(ResponseBase):
    id: str = Field(alias="_id")
    submitted_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class EvaluatorDocUpdate(BaseModel):
    evaluator_document: str


class ExamSubmissionUpdate(BaseModel):
    exam_grade: Optional[str] = None          # note finale (manuelle ou calculée)
    exam_status: str
    exam_comments: Optional[str] = None
    exam_appreciation: Optional[str] = None   # ex: "Bien", "Très bien", "Insuffisant"…
    answer_grades: Optional[List[Dict[str, Any]]] = None  # [{question_id, points_earned, max_points, comment}]


class AntiCheatUpdate(BaseModel):
    exam_document: Optional[str] = None
    cheat_alerts: list[str] = []
    exam_answers: Optional[list[Dict[str, Any]]] = None
    candidate_photos: Optional[list[str]] = None


class AssignExaminerUpdate(BaseModel):
    examiner_email: str


class FinalEvaluationUpdate(BaseModel):
    final_grade: str
    final_appreciation: str


class DocumentsValidationUpdate(BaseModel):
    documents_validation: Dict[str, Any]


class DocumentResubmitRequest(BaseModel):
    document_name: str
    message: Optional[str] = None
