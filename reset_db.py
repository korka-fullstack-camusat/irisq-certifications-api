"""
reset_db.py — Réinitialisation complète de la base irisq_db.

Conserve : users
Supprime  : responses, sessions, forms, exams, candidate_accounts,
            audit_logs, _migrations + fichiers GridFS (fs.files / fs.chunks)

Usage :
    python reset_db.py
"""

import asyncio
import os
import sys

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URI     = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

COLLECTIONS_TO_CLEAR = [
    "responses",
    "sessions",
    "forms",
    "exams",
    "candidate_accounts",
    "audit_logs",
    "_migrations",
    # GridFS
    "fs.files",
    "fs.chunks",
]


async def reset():
    if not MONGO_URI:
        print("❌  MONGO_URI introuvable dans .env")
        sys.exit(1)

    print(f"\n⚠️  Vous allez supprimer tout le contenu de [{DATABASE_NAME}]")
    print("   Collections conservées : users")
    print("   Collections vidées     :", ", ".join(COLLECTIONS_TO_CLEAR))
    confirm = input("\nTaper 'RESET' pour confirmer : ").strip()
    if confirm != "RESET":
        print("Annulé.")
        return

    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=15000,
        tls=True,
        tlsCAFile=certifi.where(),
        tlsDisableOCSPEndpointCheck=True,
    )
    db = client[DATABASE_NAME]

    total = 0
    for col_name in COLLECTIONS_TO_CLEAR:
        col = db[col_name]
        result = await col.delete_many({})
        print(f"  ✓ {col_name:<25} {result.deleted_count} document(s) supprimé(s)")
        total += result.deleted_count

    client.close()
    print(f"\n✅  Reset terminé — {total} document(s) supprimé(s) au total.")
    print("   La table 'users' est intacte.\n")


if __name__ == "__main__":
    asyncio.run(reset())
