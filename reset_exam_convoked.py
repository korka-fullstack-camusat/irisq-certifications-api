"""
reset_exam_convoked.py
----------------------
Remet exam_convoked=False pour TOUS les candidats en base.

A executer une seule fois apres le deploiement du fix exam_convoked.
Ensuite l'evaluateur doit republier les examens et selectionner les
candidats qui doivent voir le bouton Examen.

Usage :
  py reset_exam_convoked.py              -> remet a zero pour tous
  py reset_exam_convoked.py --dry-run    -> affiche combien seraient affectes
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


async def main(dry_run: bool):
    print()
    print("=" * 60)
    print("  IRISQ - Reset exam_convoked")
    print("=" * 60)

    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]

    # Compter les candidats actuellement convoked
    count_true = await db["responses"].count_documents({"exam_convoked": True})
    count_total = await db["responses"].count_documents({})

    print(f"\n  Total dossiers        : {count_total}")
    print(f"  exam_convoked = True  : {count_true}  (vont etre remis a False)")

    if dry_run:
        print("\n  [DRY-RUN] Aucune modification effectuee.")
    else:
        result = await db["responses"].update_many(
            {},
            {"$set": {"exam_convoked": False}}
        )
        print(f"\n  [OK] {result.modified_count} dossier(s) remis a exam_convoked=False")
        print()
        print("  Prochaine etape :")
        print("  → Aller sur /evaluateur/examens")
        print("  → Cliquer 'Publier' sur chaque examen")
        print("  → Selectionner les candidats qui doivent voir le bouton Examen")

    print("=" * 60)
    print()
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche le resultat sans modifier la base")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
