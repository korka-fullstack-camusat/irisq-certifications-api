import asyncio
from database import connect_to_mongo, db_instance
from database import get_fs
import os
from fpdf import FPDF
from bson import ObjectId
import datetime
import requests

async def main():
    # 1. Create a dummy Exam PDF with formatted questions
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(0, 10, "Examen de Test", ln=True)
    pdf.cell(0, 10, "PARTIE 1", ln=True)
    pdf.cell(0, 10, "1. Quelle est la capitale de la France ?", ln=True)
    pdf.cell(0, 10, "A. Paris", ln=True)
    pdf.cell(0, 10, "B. Lyon", ln=True)
    pdf.cell(0, 10, "2. Expliquez le fonctionnement du web.", ln=True)
    pdf_path = "test_exam.pdf"
    pdf.output(pdf_path)
    
    # 2. Upload it to GridFS
    await connect_to_mongo()
    db = db_instance.db
    fs = db_instance.fs
    
    with open(pdf_path, "rb") as f:
        content = f.read()
    file_id = await fs.upload_from_stream("test_exam.pdf", content, metadata={"original_name": "test_exam.pdf"})
    doc_url = f"/api/files/{str(file_id)}"
    print(f"Uploaded Exam Document: {doc_url}")
    
    # 3. Call the API to create the Exam
    create_payload = {
        "title": "Examen API Test",
        "description": "Test E2E",
        "certification": "ISO 9001",
        "document_url": doc_url
    }
    res = requests.post("http://localhost:8000/api/exams", json=create_payload)
    print("Create Exam Response:", res.json())
    
    exam_doc = res.json()
    print("Parsed Questions:", exam_doc.get("parsed_questions", []))
    
    # 4. Insert a fake Response to take the exam
    resp_id = str(ObjectId())
    await db["responses"].insert_one({
        "_id": ObjectId(resp_id),
        "form_id": str(ObjectId()),
        "name": "Test Candidate",
        "email": "test@candidate.com",
        "profile": "Student",
        "answers": {"Certification souhaitée": "ISO 9001"},
        "status": "approved",
        "candidate_id": "CAND-TEST1",
        "submitted_at": datetime.datetime.utcnow()
    })
    
    # 5. Call Anti-Cheat endpoint to submit answers
    submit_payload = {
        "exam_answers": [
            {"question_id": exam_doc["parsed_questions"][0]["id"] if exam_doc.get("parsed_questions") else "q1", "answer": "Paris"},
            {"question_id": exam_doc["parsed_questions"][1]["id"] if len(exam_doc.get("parsed_questions", [])) > 1 else "q2", "answer": "C'est un réseau complexe."}
        ],
        "cheat_alerts": ["Perte de focus"]
    }
    
    res_submit = requests.patch(f"http://localhost:8000/api/responses/{resp_id}/anti-cheat", json=submit_payload)
    print("Submit Exam Response:", res_submit.json())

if __name__ == "__main__":
    asyncio.run(main())
