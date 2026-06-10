"""
supprimer_examens_passes.py — Supprime les dossiers candidats dont l'EXAMEN
est au statut "Passe" (c.-à-d. ceux qui ont déjà composé : exam_answers ou
exam_document présents), selon la même logique que suivi.py.

Exécution : python supprimer_examens_passes.py
  - Affiche d'abord la liste des dossiers concernés
  - Demande une confirmation explicite avant toute suppression
  - Supprime les documents correspondants dans la collection "responses"
"""

import asyncio
import os
import certifi
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=certifi.where())
    db = client[os.getenv("DATABASE_NAME", "irisq_db")]
    collection = db["responses"]

    candidats = await collection.find({}).sort("submitted_at", 1).to_list(1000)

    # --- Sélection : EXAMEN = "Passe" (même logique que suivi.py) ---
    a_supprimer = [c for c in candidats if c.get("exam_answers") or c.get("exam_document")]

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    print()
    print("=" * 108)
    print(f"  SUPPRESSION DES DOSSIERS — EXAMEN = Passe  —  {now}")
    print("=" * 108)

    if not a_supprimer:
        print("  Aucun dossier avec EXAMEN = Passe trouvé. Rien à supprimer.")
        print("=" * 108)
        print()
        client.close()
        return

    print(f"  {len(a_supprimer)} dossier(s) seront supprimés définitivement :")
    print("-" * 108)
    print(f"  {'#':<4} {'NOM':<26} {'FORMATION':<34} {'PUBLIC_ID'}")
    print("-" * 108)

    for i, c in enumerate(a_supprimer, 1):
        answers = c.get("answers") or {}
        certification = (
            answers.get("Certification souhaitée")
            or answers.get("Certification souhaitee")
            or "N/A"
        )
        name = c.get("name", "N/A")
        public_id = c.get("public_id", "N/A")
        print(f"  {i:<4} {name[:25]:<26} {certification[:33]:<34} {public_id}")

    print("=" * 108)
    print()

    reponse = input(
        f"  ⚠️  Confirmez-vous la suppression DÉFINITIVE de ces {len(a_supprimer)} dossier(s) ? "
        f"(tapez 'OUI' en majuscules pour confirmer) : "
    ).strip()

    if reponse != "OUI":
        print()
        print("  Suppression annulée. Aucune modification n'a été effectuée.")
        print()
        client.close()
        return

    ids = [c["_id"] for c in a_supprimer]
    result = await collection.delete_many({"_id": {"$in": ids}})

    print()
    print(f"  ✅ {result.deleted_count} dossier(s) supprimé(s) avec succès.")
    print("=" * 108)
    print()

    client.close()


asyncio.run(main())
