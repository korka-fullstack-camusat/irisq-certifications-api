"""
send_all_credentials.py
-----------------------
Envoie les identifiants de connexion a tous les candidats existants.
Un nouveau mot de passe temporaire est genere pour chaque candidat,
la base est mise a jour, et l'email est envoye via Brevo.

Usage :
  py send_all_credentials.py --dry-run          -> apercu sans rien faire
  py send_all_credentials.py                    -> envoie a tous
  py send_all_credentials.py --email x@y.com   -> un seul candidat
"""

import asyncio
import argparse
import secrets
import sys
import os
import certifi

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from email_service import notify_candidate_submission_received

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def gen_password() -> str:
    return secrets.token_urlsafe(6)[:8]


# ─────────────────────────────────────────────────────────────────────────────

async def main(dry_run: bool, filter_email: str | None):
    print()
    print("=" * 62)
    print("  IRISQ - Envoi des identifiants a tous les candidats")
    print("=" * 62)

    if not MONGO_URI:
        print("[ERREUR] MONGO_URI manquant dans .env")
        sys.exit(1)

    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]
    print(f"\n[DB] Connecte a {DATABASE_NAME}")

    # ── Requete : tous les dossiers avec public_id + email ────────────────────
    query = {
        "public_id": {"$exists": True, "$ne": None, "$ne": ""},
        "email":     {"$exists": True, "$ne": None, "$ne": ""},
    }
    if filter_email:
        query["email"] = filter_email.strip().lower()

    all_docs = await db["responses"].find(query).sort("submitted_at", 1).to_list(length=None)

    if not all_docs:
        print("\n[INFO] Aucun candidat trouve.")
        client.close()
        return

    # ── Un seul traitement par public_id (dedoublonnage) ─────────────────────
    seen: dict = {}
    for doc in all_docs:
        pid = doc.get("public_id", "")
        if pid and pid not in seen:
            seen[pid] = doc

    candidates = list(seen.values())

    print(f"\n[INFO] {len(candidates)} candidat(s) unique(s) trouve(s)\n")
    if dry_run:
        print("[!] DRY-RUN : aucun email, aucune modification en base\n")

    print("-" * 62)

    ok_count   = 0
    fail_count = 0
    skip_count = 0

    for i, doc in enumerate(candidates, 1):
        public_id = doc.get("public_id", "")
        email     = (doc.get("email") or "").strip()
        name      = (doc.get("name")  or "Candidat").strip()

        # Toutes les certifications de ce candidat
        sibling_docs = await db["responses"].find({"public_id": public_id}).to_list(length=None)
        certifications = list({
            d.get("answers", {}).get("Certification souhait\xe9e", "")
            or d.get("answers", {}).get("Certification souhaitee", "")
            for d in sibling_docs
        } - {""})
        if not certifications:
            certifications = ["Non specifiee"]

        print(f"[{i:>2}/{len(candidates)}]  {name}")
        print(f"         Email     : {email}")
        print(f"         Public ID : {public_id}")
        print(f"         Cert(s)   : {', '.join(certifications)}")

        if not email:
            print("         => IGNORE (pas d'email)\n")
            skip_count += 1
            continue

        if dry_run:
            print("         => [DRY-RUN]\n")
            continue

        # Nouveau mot de passe temporaire
        temp_pwd = gen_password()
        new_hash = hash_password(temp_pwd)

        # Mise a jour en base (tous les dossiers de ce candidat)
        await db["responses"].update_many(
            {"public_id": public_id},
            {"$set": {
                "password_hash":        new_hash,
                "must_change_password": True,
            }}
        )

        # Envoi email
        sent = notify_candidate_submission_received(
            to_email         = email,
            candidate_name   = name,
            public_id        = public_id,
            certifications   = certifications,
            default_password = temp_pwd,
        )

        if sent:
            print(f"         => OK  (mdp : {temp_pwd})\n")
            ok_count += 1
        else:
            print("         => ECHEC (verifier Brevo)\n")
            fail_count += 1

    # ── Resume ────────────────────────────────────────────────────────────────
    print("=" * 62)
    print("  RESUME")
    print("=" * 62)
    if dry_run:
        print(f"  Candidats trouves   : {len(candidates)}")
        print("  Aucun email envoye  (mode dry-run)")
    else:
        print(f"  OK      : {ok_count}")
        print(f"  Echecs  : {fail_count}")
        print(f"  Ignores : {skip_count}")
        print(f"  Total   : {len(candidates)}")
    print("=" * 62)
    print()

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Apercu sans envoi ni modification")
    parser.add_argument("--email", type=str, default=None,
                        help="Cibler un seul candidat par email")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, filter_email=args.email))
