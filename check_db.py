import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def check():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["form_builder"]
    
    # 1. Check if we have an exam with parsed questions
    exam = await db["exams"].find_one({}, sort=[("created_at", -1)])
    if exam:
        print(f"Latest exam: {exam['certification']}")
        print(f"Parsed questions: {len(exam.get('parsed_questions', []))}")
        if exam.get('parsed_questions'):
            print(exam['parsed_questions'][0:1])
    else:
        print("No exams found.")

    # 2. Check if we have a response with exam_document as a PDF
    resp = await db["responses"].find_one({"exam_document": {"$regex": "\.pdf$|/api/files/"}}, sort=[("_id", -1)])
    if resp:
        print(f"Latest response with PDF: {resp['_id']}")
        print(f"PDF URL: {resp['exam_document']}")
    else:
        print("No responses with generated PDF found.")

if __name__ == "__main__":
    asyncio.run(check())
