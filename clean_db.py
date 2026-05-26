"""
clean_db.py — Vide toutes les collections SAUF 'users'.
Utilise la même connexion MongoDB que l'application (via .env).

Exécution :
    python clean_db.py
"""

import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import certifi

load_dotenv()

MONGO_URI     = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

# Collections à ne JAMAIS toucher
PROTECTED = {"users"}

async def clean():
    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=10000,
        tls=True,
        tlsCAFile=certifi.where(),
    )
    db = client[DATABASE_NAME]

    # Liste toutes les collections existantes
    all_collections = await db.list_collection_names()
    to_delete = [c for c in all_collections if c not in PROTECTED]

    if not to_delete:
        print("[OK] Aucune collection a supprimer (base deja vide ou seulement 'users').")
        client.close()
        return

    print(f"Base de donnees : {DATABASE_NAME}")
    print(f"Collections protegees : {PROTECTED}")
    print(f"\nCollections qui seront videes ({len(to_delete)}) :")
    for c in to_delete:
        count = await db[c].count_documents({})
        print(f"  - {c:<30} {count} document(s)")

    print("\n[!] Cette action est IRREVERSIBLE.")
    confirm = input("Tapez 'SUPPRIMER' pour confirmer : ").strip()

    if confirm != "SUPPRIMER":
        print("[x] Annule.")
        client.close()
        return

    print("\nSuppression en cours...")
    total_deleted = 0
    for c in to_delete:
        result = await db[c].delete_many({})
        print(f"  [OK] {c:<30} {result.deleted_count} document(s) supprime(s)")
        total_deleted += result.deleted_count

    # Vider aussi GridFS (fs.files + fs.chunks) si present
    for gridfs_col in ["fs.files", "fs.chunks"]:
        if gridfs_col in all_collections:
            result = await db[gridfs_col].delete_many({})
            print(f"  [OK] {gridfs_col:<30} {result.deleted_count} document(s) supprime(s)")
            total_deleted += result.deleted_count

    print(f"\n[DONE] Nettoyage termine - {total_deleted} document(s) supprime(s) au total.")
    print(f"       La collection 'users' est intacte.")
    client.close()

if __name__ == "__main__":
    asyncio.run(clean())
