"""
delete_candidates.py — Supprime les candidats par email dans responses + candidate_accounts.
Execution : python delete_candidates.py
"""

import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import certifi

load_dotenv()

MONGO_URI     = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

# Emails des candidats a supprimer
EMAILS_TO_DELETE = [
    "korka.camusat30@gmail.com",
    "ak.mahrez@gmail.com",
]

async def delete_candidates():
    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=10000,
        tls=True,
        tlsCAFile=certifi.where(),
    )
    db = client[DATABASE_NAME]

    print("=" * 55)
    print("SUPPRESSION CANDIDATS PAR EMAIL")
    print("=" * 55)
    print(f"Base : {DATABASE_NAME}")
    print(f"Emails cibles : {EMAILS_TO_DELETE}")
    print()

    # --- Apercu avant suppression ---
    print("Documents trouves AVANT suppression :")
    print()

    for email in EMAILS_TO_DELETE:
        query = {"$or": [
            {"email": {"$regex": f"^{email}$", "$options": "i"}},
            {"answers.Email": {"$regex": f"^{email}$", "$options": "i"}},
        ]}

        resp_count = await db["responses"].count_documents(query)
        acct_count = await db["candidate_accounts"].count_documents(
            {"email": {"$regex": f"^{email}$", "$options": "i"}}
        )

        print(f"  {email}")
        print(f"    - responses          : {resp_count} document(s)")
        print(f"    - candidate_accounts : {acct_count} document(s)")

    print()
    print("[!] Cette action est IRREVERSIBLE.")
    confirm = input("Tapez 'SUPPRIMER' pour confirmer : ").strip()

    if confirm != "SUPPRIMER":
        print("[x] Annule.")
        client.close()
        return

    print()
    print("Suppression en cours...")

    total = 0
    for email in EMAILS_TO_DELETE:
        query_resp = {"$or": [
            {"email": {"$regex": f"^{email}$", "$options": "i"}},
            {"answers.Email": {"$regex": f"^{email}$", "$options": "i"}},
        ]}
        query_acct = {"email": {"$regex": f"^{email}$", "$options": "i"}}

        r1 = await db["responses"].delete_many(query_resp)
        r2 = await db["candidate_accounts"].delete_many(query_acct)

        print(f"  {email}")
        print(f"    [OK] responses          : {r1.deleted_count} supprime(s)")
        print(f"    [OK] candidate_accounts : {r2.deleted_count} supprime(s)")
        total += r1.deleted_count + r2.deleted_count

    print()
    print(f"[DONE] {total} document(s) supprimes au total.")
    client.close()

if __name__ == "__main__":
    asyncio.run(delete_candidates())
