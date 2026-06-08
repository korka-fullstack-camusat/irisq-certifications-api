"""
delete_passed_exams.py
----------------------
Supprime tous les dossiers (responses) dont EXAMEN = "Passe"
(c'est-a-dire ceux qui ont des exam_answers ou un exam_document),
selon la meme logique que suivi.py.

Usage :
  py delete_passed_exams.py             (avec confirmation)
  py delete_passed_exams.py --dry-run   (affiche seulement, ne supprime rien)
  py delete_passed_exams.py --yes       (supprime sans demander confirmation)
"""

import asyncio
import argparse
import os
import certifi
from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")


async def main(dry_run: bool, yes: bool):
    print()
    print("=" * 70)
    print("  IRISQ - Suppression des dossiers avec EXAMEN = Passe")
    print("=" * 70)

    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]

    # Meme critere que suivi.py pour le label "Passe"
    query = {"$or": [{"exam_answers": {"$exists": True, "$ne": None}},
                     {"exam_document": {"$exists": True, "$ne": None}}]}

    dossiers = await db["responses"].find(query).to_list(length=None)

    if not dossiers:
        print("\n  Aucun dossier avec EXAMEN = Passe.\n")
        client.close()
        return

    print(f"\n  {len(dossiers)} dossier(s) trouve(s) :\n")
    for d in dossiers:
        answers = d.get("answers") or {}
        cert = (answers.get("Certification souhaitée")
                or answers.get("Certification souhaitee")
                or "N/A")
        print(f"  - {d.get('name', 'N/A'):<26} | {d.get('public_id', '?'):<14} | {cert}")

    print()

    if dry_run:
        print("  [DRY-RUN] Aucune suppression effectuee.\n")
        client.close()
        return

    if not yes:
        confirm = input("  Confirmer la suppression de ces dossiers ? (oui/non) : ").strip().lower()
        if confirm not in ("oui", "o", "yes", "y"):
            print("  Annule.\n")
            client.close()
            return

    ids = [d["_id"] for d in dossiers]
    res = await db["responses"].delete_many({"_id": {"$in": ids}})

    print()
    print(f"  [OK] Dossiers supprimes : {res.deleted_count}")
    print("=" * 70)
    print()

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les dossiers concernes sans rien supprimer")
    parser.add_argument("--yes", action="store_true",
                        help="Supprime sans demander confirmation")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run, yes=args.yes))
