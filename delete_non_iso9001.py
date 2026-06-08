"""
delete_non_iso9001.py
---------------------
Supprime tous les dossiers (responses) dont la certification est DIFFERENTE de :
  - "Junior Implementor ISO 9001:2015"
  - "Implementor ISO 9001:2015"
et envoie a chaque candidat concerne un email l'informant que son dossier a ete
supprime dans le cadre d'une maintenance de la plateforme.

Usage :
  py delete_non_iso9001.py             (avec confirmation)
  py delete_non_iso9001.py --dry-run   (affiche seulement, ne supprime/n'envoie rien)
  py delete_non_iso9001.py --yes       (supprime + envoie sans demander confirmation)
  py delete_non_iso9001.py --no-email  (supprime sans envoyer d'email)
"""

import asyncio
import argparse
import os
import certifi
from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from email_service import notify_candidate_data_deleted

MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

KEPT_CERTIFICATIONS = {
    "Junior Implementor ISO 9001:2015",
    "Implementor ISO 9001:2015",
}


def get_certification(d: dict) -> str:
    answers = d.get("answers") or {}
    return (answers.get("Certification souhaitée")
            or answers.get("Certification souhaitee")
            or "N/A")


async def main(dry_run: bool, yes: bool, send_emails: bool):
    print()
    print("=" * 70)
    print("  IRISQ - Suppression des dossiers hors ISO 9001:2015 (maintenance)")
    print("=" * 70)

    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]

    dossiers = await db["responses"].find({}).to_list(length=None)
    a_supprimer = [d for d in dossiers if get_certification(d) not in KEPT_CERTIFICATIONS]

    if not a_supprimer:
        print("\n  Aucun dossier a supprimer.\n")
        client.close()
        return

    print(f"\n  {len(a_supprimer)} dossier(s) a supprimer (certification != ISO 9001:2015) :\n")
    for d in a_supprimer:
        print(f"  - {d.get('name', 'N/A'):<26} | {d.get('public_id', '?'):<14} | {d.get('email', '?'):<35} | {get_certification(d)}")

    print()

    if dry_run:
        print("  [DRY-RUN] Aucune suppression ni email envoye.\n")
        client.close()
        return

    if not yes:
        confirm = input("  Confirmer la suppression de ces dossiers et l'envoi des emails ? (oui/non) : ").strip().lower()
        if confirm not in ("oui", "o", "yes", "y"):
            print("  Annule.\n")
            client.close()
            return

    print()

    # ── Envoyer les emails AVANT suppression (pour disposer encore des infos) ──
    if send_emails:
        envoyes = 0
        for d in a_supprimer:
            email = d.get("email")
            if not email:
                continue
            try:
                notify_candidate_data_deleted(
                    to_email         = email,
                    candidate_name   = d.get("name", "Candidat"),
                    public_id        = d.get("public_id", "?"),
                    certification    = get_certification(d),
                )
                envoyes += 1
            except Exception as e:
                print(f"  [ERREUR email] {email} : {e}")
        print(f"  [OK] Emails de notification envoyes : {envoyes}")

    # ── Supprimer les dossiers ─────────────────────────────────────────────────
    ids = [d["_id"] for d in a_supprimer]
    res = await db["responses"].delete_many({"_id": {"$in": ids}})
    print(f"  [OK] Dossiers supprimes              : {res.deleted_count}")

    print()
    print("=" * 70)
    print()

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les dossiers concernes sans rien supprimer ni envoyer")
    parser.add_argument("--yes", action="store_true",
                        help="Supprime et envoie sans demander confirmation")
    parser.add_argument("--no-email", action="store_true",
                        help="Supprime sans envoyer d'email aux candidats")
    args = parser.parse_args()

    asyncio.run(main(
        dry_run     = args.dry_run,
        yes         = args.yes,
        send_emails = not args.no_email,
    ))
