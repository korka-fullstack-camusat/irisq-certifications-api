import asyncio
import requests
from database import connect_to_mongo, db_instance

async def test_anti_cheat_pdf():
    await connect_to_mongo()
    db = db_instance.db
    
    # 1. Choose any response to simulate submission
    resp = await db["responses"].find_one({}, sort=[("_id", -1)])
    if not resp:
        print("No response found.")
        return
        
    resp_id = str(resp["_id"])
    print(f"Testing PDF generation on Response ID: {resp_id}")
    
    # 2. Setup mock answers and alerts
    payload = {
        "exam_answers": [
            {"question_id": "q1", "answer": "Je pense que c’est une bonne chose l’ISO. Ça marche à 100% avec des caractères spéciaux comme œ et €."},
            {"question_id": "q2", "answer": "L'exigence 4.1 de l'ISO 17025."}
        ],
        "cheat_alerts": [
            "L'utilisateur a quitté le mode plein écran à 10:45",
            "Copier/Coller détecté (« ctrl+c »)"
        ],
        "exam_document": "/api/files/test_id"
    }
    
    # 3. Hit the endpoint
    res = requests.patch(f"http://localhost:8000/api/responses/{resp_id}/anti-cheat", json=payload)
    
    print("Anti-Cheat Status:", res.status_code)
    try:
        data = res.json()
        print("Generated exam_document URL:", data.get("exam_document"))
        print("SUCCESS" if "api/files" in str(data.get("exam_document")) else "FAILED")
    except Exception as e:
        print(f"Error parsing response: {e}")

if __name__ == "__main__":
    asyncio.run(test_anti_cheat_pdf())
