import asyncio
import requests
from database import connect_to_mongo, db_instance

async def test_final_evaluation():
    await connect_to_mongo()
    db = db_instance.db
    
    # Check if there is a response with exam_document (completed by candidate)
    resp = await db["responses"].find_one({"exam_document": {"$ne": None}}, sort=[("_id", -1)])
    
    if not resp:
        print("No response with an exam document found.")
        return
        
    resp_id = str(resp["_id"])
    print(f"Testing final evaluation on Response ID: {resp_id}")
    
    # 1. Simulate a corrector grading the exam first
    grade_payload = {
        "exam_grade": "16/20",
        "exam_status": "Acquis",
        "exam_comments": "Bonne compréhension globale."
    }
    
    # We didn't create a specific route for the corrector in our recent plan, but let's assume it exists or we update DB directly for the test
    # Actually, phase 7 mentions `PATCH /api/responses/{id}/grade` which is probably implemented. Let's update DB directly to be sure and fast.
    await db["responses"].update_one(
        {"_id": resp["_id"]},
        {"$set": grade_payload}
    )
    print("Simulated Corrector Grading.")
    
    # 2. Test the new evaluator final evaluation endpoint
    eval_payload = {
        "final_grade": "Admis",
        "final_appreciation": "Excellent profil, certifié."
    }
    
    res = requests.patch(f"http://localhost:8000/api/responses/{resp_id}/final-evaluation", json=eval_payload)
    
    print("Final Evaluation Status:", res.status_code)
    try:
        data = res.json()
        print("Final Grade:", data.get("final_grade"))
        print("Final Appreciation:", data.get("final_appreciation"))
        print("Status:", data.get("status"))
        
        if data.get("status") == "evaluated":
            print("SUCCESS: Endpoint works correctly.")
        else:
            print("FAILED: Status was not updated.")
    except Exception as e:
        print(f"Error parsing response: {e}")

if __name__ == "__main__":
    asyncio.run(test_final_evaluation())
