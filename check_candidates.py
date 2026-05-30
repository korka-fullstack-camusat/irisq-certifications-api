"""
check_candidates.py — Verifie la presence des candidats et supprime si trouves.
"""
import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

EMAILS = ["korka.camusat30@gmail.com", "ak.mahrez@gmail.com"]

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=certifi.where())
    db = client[os.getenv("DATABASE_NAME", "irisq_db")]

    # --- Afficher la structure d'un document ---
    print("=== Structure responses (1er doc) ===")
    sample = await db["responses"].find_one({})
    if sample:
        print("Cles:", list(sample.keys()))
        print("email:", sample.get("email"))
        answers = sample.get("answers") or {}
        print("answers (cles):", list(answers.keys())[:10])
        # Chercher toutes les cles qui ressemblent a email
        email_keys = [k for k in answers.keys() if "mail" in k.lower() or "email" in k.lower()]
        print("Cles answers contenant 'email':", email_keys)
        for k in email_keys:
            print(f"  answers[{k}] = {answers[k]}")
    print()

    # --- Chercher les candidats ---
    print("=== Recherche des candidats cibles ===")
    all_responses = await db["responses"].find({}).to_list(1000)
    print(f"Total responses en base: {len(all_responses)}")
    print()

    ids_to_delete = []
    for email in EMAILS:
        print(f"Recherche: {email}")
        found = []
        for doc in all_responses:
            doc_email = str(doc.get("email") or "").lower()
            answers = doc.get("answers") or {}
            # Chercher dans tous les champs answers qui contiennent "mail"
            answers_emails = " ".join(str(v) for k, v in answers.items() if "mail" in k.lower()).lower()

            if email.lower() in doc_email or email.lower() in answers_emails:
                found.append(doc)
                ids_to_delete.append(doc["_id"])
                print(f"  -> TROUVE: name={doc.get('name')} | email={doc.get('email')} | id={doc['_id']}")

        if not found:
            print(f"  -> PAS TROUVE dans responses")

        # Verifier candidate_accounts
        acct = await db["candidate_accounts"].find_one({"email": {"$regex": email, "$options": "i"}})
        if acct:
            print(f"  -> TROUVE dans candidate_accounts: {acct.get('email')}")
        else:
            print(f"  -> PAS dans candidate_accounts")
        print()

    if not ids_to_delete:
        print("Aucun document a supprimer — les candidats ne sont pas en base.")
        print("La page affiche peut-etre des donnees en cache (rafraichir le navigateur).")
        client.close()
        return

    print(f"=== {len(ids_to_delete)} document(s) a supprimer ===")
    confirm = input("Tapez 'SUPPRIMER' pour confirmer : ").strip()

    if confirm != "SUPPRIMER":
        print("[x] Annule.")
        client.close()
        return

    from bson import ObjectId
    for oid in ids_to_delete:
        r = await db["responses"].delete_one({"_id": oid})
        print(f"  Supprime responses _id={oid} -> {r.deleted_count}")

    for email in EMAILS:
        r = await db["candidate_accounts"].delete_many({"email": {"$regex": email, "$options": "i"}})
        if r.deleted_count:
            print(f"  Supprime candidate_accounts email={email} -> {r.deleted_count}")

    print("[DONE] Suppression terminee.")
    client.close()

asyncio.run(main())
