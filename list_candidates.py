"""
list_candidates.py — Liste tous les candidats avec leur statut et examen.
Execution : python list_candidates.py
"""

import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI     = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

STATUS_LABELS = {
    "pending" : "En attente",
    "approved": "Valide",
    "rejected": "Refuse",
}

async def main():
    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db = client[DATABASE_NAME]

    candidates = await db["responses"].find({}).sort("submitted_at", 1).to_list(1000)

    print("=" * 100)
    print(f"  CANDIDATS ({len(candidates)} dossiers)")
    print("=" * 100)
    print(f"  {'#':<4} {'NOM':<25} {'FORMATION':<35} {'STATUT':<12} {'ID PUBLIC':<18} {'EXAMEN'}")
    print("-" * 100)

    for i, c in enumerate(candidates, 1):
        answers       = c.get("answers") or {}
        certification = (
            answers.get("Certification souhaitée")
            or answers.get("Certification souhaitee")
            or "N/A"
        )
        name      = c.get("name", "N/A")
        public_id = c.get("public_id", "N/A")
        status    = STATUS_LABELS.get(c.get("status", ""), "N/A")

        # Examen passe ou non
        exam_answers = c.get("exam_answers")
        exam_status  = c.get("exam_status")
        exam_doc     = c.get("exam_document")

        if exam_answers or exam_doc:
            examen = "Passe"
        elif c.get("exam_token"):
            examen = "Convoque"
        else:
            examen = "Non passe"

        print(f"  {i:<4} {name:<25} {certification[:34]:<35} {status:<12} {public_id:<18} {examen}")

    print("=" * 100)
    client.close()

asyncio.run(main())
