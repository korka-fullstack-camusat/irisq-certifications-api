from pydantic import BaseModel, Field, EmailStr
from typing import Dict, Any, Optional
from datetime import datetime


class ResponseBase(BaseModel):
    form_id: Optional[str] = None
    session_id: Optional[str] = None
    name: str
    email: EmailStr
    profile: str
    answers: Dict[str, Any]
    score: Optional[str] = None
    status: str = "pending"
    candidate_id: Optional[str] = None
    candidat_account_id: Optional[str] = None
    public_id: Optional[str] = None
    exam_token: Optional[str] = None
    evaluator_document: Optional[str] = None

    exam_document: Optional[str] = None
    exam_grade: Optional[str] = None
    exam_status: Optional[str] = None
    exam_comments: Optional[str] = None

    final_grade: Optional[str] = None
    final_appreciation: Optional[str] = None

    cheat_alerts: Optional[list[str]] = None
    exam_answers: Optional[list[Dict[str, Any]]] = None
    assigned_examiner_email: Optional[str] = None
    candidate_photos: Optional[list[str]] = None

    documents_validation: Optional[Dict[str, Any]] = None

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
    exam_grade: str
    exam_status: str
    exam_comments: Optional[str] = None


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
