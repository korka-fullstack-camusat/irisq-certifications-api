from fastapi import APIRouter, HTTPException, Body
from database import get_database
from models.form import FormCreate, FormBase
from bson import ObjectId
from datetime import datetime

router = APIRouter()

def serialize_doc(doc):
    doc["_id"] = str(doc["_id"])
    return doc

@router.post("", response_description="Create a new form", status_code=201)
async def create_form(form: FormCreate = Body(...)):
    db = get_database()
    form_dict = form.model_dump()
    form_dict["created_at"] = datetime.utcnow()
    form_dict["updated_at"] = datetime.utcnow()
    form_dict["responses_count"] = 0

    new_form = await db["forms"].insert_one(form_dict)
    created_form = await db["forms"].find_one({"_id": new_form.inserted_id})
    return serialize_doc(created_form)

@router.get("", response_description="List all forms")
async def list_forms():
    db = get_database()
    forms = await db["forms"].find().to_list(1000)
    return [serialize_doc(f) for f in forms]

@router.get("/{id}", response_description="Get a single form")
async def get_form(id: str):
    db = get_database()
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    form = await db["forms"].find_one({"_id": ObjectId(id)})
    if form is not None:
        return serialize_doc(form)
    raise HTTPException(status_code=404, detail=f"Form {id} not found")
