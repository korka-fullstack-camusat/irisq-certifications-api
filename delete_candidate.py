"""
delete_candidate.py
-------------------
Supprime TOUTES les donnees d'un candidat par public_id ou email.
Utiliser pour remettre a zero un candidat afin de retester le flow complet.

Usage :
  py delete_candidate.py --public-id IC26D01L-0018
  py delete_candidate.py --email diallo30amadoukorka@gmail.com
  py delete_candidate.py --public-id IC26D01L-0018 --dry-run
"""

import asyncio
import argparse
import os
import sys
import certifi
from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")


async def main(public_id: str | None, email: str | None, dry_run: bool):
    print()
    print("=" * 62)
    print("  IRISQ - Suppression complete d'un candidat")
    print("=" * 62)

    if not public_id and not email:
        print("[ERREUR] Fournir --public-id ou --email")
        sys.exit(1)

    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]

    # ── Construire la requete de recherche ────────────────────────────────────
    if public_id:
        query = {"public_id": public_id}
    else:
        query = {"email": email.strip().lower()}

    # ── Trouver tous les dossiers concernes ───────────────────────────────────
    dossiers = await db["responses"].find(query).to_list(length=None)

    if not dossiers:
        print(f"\n  Aucun dossier trouve pour : {public_id or email}")
        client.close()
        return

    print(f"\n  Candidat trouve  : {dossiers[0].get('name', 'Inconnu')}")
    print(f"  Public ID        : {dossiers[0].get('public_id', '?')}")
    print(f"  Email            : {dossiers[0].get('email', '?')}")
    print(f"  Dossiers trouves : {len(dossiers)}")
    print()

    # Afficher les dossiers
    for d in dossiers:
        cert   = d.get("answers", {}).get("Certification souhaitée", "?")
        status = d.get("status", "?")
        exam_s = d.get("exam_status", "-")
        print(f"  - {cert}  |  Dossier: {status}  |  Examen: {exam_s or '-'}")

    print()

    if dry_run:
        print("  [DRY-RUN] Aucune suppression effectuee.\n")
        client.close()
        return

    # ── Confirmation ──────────────────────────────────────────────────────────
    confirm = input("  Confirmer la suppression ? (oui/non) : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("  Annule.\n")
        client.close()
        return

    print()

    # ── Recuperer les public_ids concernes ────────────────────────────────────
    pids = list({d.get("public_id") for d in dossiers if d.get("public_id")})

    # ── 1. Supprimer les dossiers (responses) ─────────────────────────────────
    res1 = await db["responses"].delete_many({"public_id": {"$in": pids}})
    print(f"  [OK] Dossiers supprimes            : {res1.deleted_count}")

    # ── 2. Supprimer le compte candidat (candidate_accounts) ──────────────────
    res2 = await db["candidate_accounts"].delete_many({"public_id": {"$in": pids}})
    print(f"  [OK] Comptes candidats supprimes   : {res2.deleted_count}")

    # ── 3. Supprimer les sessions candidat si elles existent ─────────────────
    res3 = await db["candidate_sessions"].delete_many({"public_id": {"$in": pids}})
    print(f"  [OK] Sessions supprimees           : {res3.deleted_count}")

    print()
    print("  Toutes les donnees ont ete supprimees.")
    print("  Le candidat peut maintenant re-candidater depuis le debut.")
    print("=" * 62)
    print()

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-id", type=str, default=None,
                        help="Public ID du candidat (ex: IC26D01L-0018)")
    parser.add_argument("--email", type=str, default=None,
                        help="Email du candidat")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche ce qui serait supprime sans rien faire")
    args = parser.parse_args()

    asyncio.run(main(
        public_id = args.public_id,
        email     = args.email,
        dry_run   = args.dry_run,
    ))
