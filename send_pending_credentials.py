"""
send_pending_credentials.py
---------------------------
Envoie les identifiants UNIQUEMENT aux candidats qui n'ont pas
encore recu leur email de confirmation (credentials_sent != True).

Apres chaque envoi reussi, le champ credentials_sent=True est
ecrit en base => relancer le script plusieurs fois est sans risque,
les candidats deja notifies ne recevront pas de doublon.

Usage :
  py send_pending_credentials.py --dry-run    -> apercu, rien ne change
  py send_pending_credentials.py              -> envoie aux non-notifies
  py send_pending_credentials.py --all        -> force le renvoi a TOUS
  py send_pending_credentials.py --email x@y  -> un seul candidat
"""

import asyncio
import argparse
import secrets
import sys
import os
import certifi
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from email_service import notify_candidate_submission_received

MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)

def gen_password() -> str:
    return secrets.token_urlsafe(6)[:8]


async def main(dry_run: bool, force_all: bool, filter_email: str | None):
    print()
    print("=" * 64)
    print("  IRISQ - Envoi identifiants (candidats non encore notifies)")
    print("=" * 64)

    if not MONGO_URI:
        print("[ERREUR] MONGO_URI manquant dans .env")
        sys.exit(1)

    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]
    print(f"\n[DB] Connecte a {DATABASE_NAME}")

    # ── Requete : candidats NON encore notifies (ou --all pour tous) ──────────
    query = {
        "public_id": {"$exists": True, "$ne": None, "$ne": ""},
        "email":     {"$exists": True, "$ne": None, "$ne": ""},
    }

    if not force_all:
        # Seulement ceux sans flag credentials_sent
        query["credentials_sent"] = {"$ne": True}

    if filter_email:
        query["email"] = filter_email.strip().lower()

    all_docs = await db["responses"].find(query).sort("submitted_at", 1).to_list(length=None)

    # Dedoublonnage par public_id
    seen: dict = {}
    for doc in all_docs:
        pid = doc.get("public_id", "")
        if pid and pid not in seen:
            seen[pid] = doc

    candidates = list(seen.values())

    # Compter ceux deja notifies (pour info)
    total_with_flag = await db["responses"].count_documents({
        "public_id":         {"$exists": True, "$ne": None, "$ne": ""},
        "credentials_sent":  True,
    })
    already_sent_pids = set()
    async for d in db["responses"].find({"credentials_sent": True}, {"public_id": 1}):
        already_sent_pids.add(d.get("public_id", ""))

    print(f"\n  Deja notifies    : {len(already_sent_pids)} candidat(s)")
    print(f"  A notifier       : {len(candidates)} candidat(s)")
    if force_all:
        print("  Mode             : --all (force renvoi a tous)")
    print()

    if not candidates:
        print("[OK] Tous les candidats ont deja recu leur email.\n")
        client.close()
        return

    if dry_run:
        print("[!] DRY-RUN : aucun email, aucune modification\n")

    print("-" * 64)

    ok_count   = 0
    fail_count = 0
    skip_count = 0

    for i, doc in enumerate(candidates, 1):
        public_id = doc.get("public_id", "")
        email     = (doc.get("email") or "").strip()
        name      = (doc.get("name")  or "Candidat").strip()

        # Toutes les certifications de ce candidat
        siblings = await db["responses"].find({"public_id": public_id}).to_list(length=None)
        certifications = list({
            d.get("answers", {}).get("Certification souhait\xe9e", "")
            or d.get("answers", {}).get("Certification souhaitee", "")
            for d in siblings
        } - {""})
        if not certifications:
            certifications = ["Non specifiee"]

        status_flag = "[DEJA ENVOYE]" if doc.get("credentials_sent") else "[NON NOTIFIE]"

        print(f"[{i:>2}/{len(candidates)}]  {name}  {status_flag}")
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

        # Mise a jour en base
        now_utc = datetime.now(timezone.utc)
        await db["responses"].update_many(
            {"public_id": public_id},
            {"$set": {
                "password_hash":        new_hash,
                "must_change_password": True,
                "credentials_sent":     True,
                "credentials_sent_at":  now_utc,
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
            # En cas d'echec, retirer le flag pour pouvoir reessayer
            await db["responses"].update_many(
                {"public_id": public_id},
                {"$set": {"credentials_sent": False}}
            )
            print("         => ECHEC (verifier Brevo — flag reinitialise)\n")
            fail_count += 1

    # ── Resume ────────────────────────────────────────────────────────────────
    print("=" * 64)
    print("  RESUME")
    print("=" * 64)
    if dry_run:
        print(f"  A notifier  : {len(candidates)}")
        print("  [DRY-RUN]   aucun email envoye")
    else:
        print(f"  OK      : {ok_count}")
        print(f"  Echecs  : {fail_count}  (relancer le script pour reessayer)")
        print(f"  Ignores : {skip_count}")
        print(f"  Total   : {len(candidates)}")
    print("=" * 64)
    print()

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true",
                        help="Apercu sans envoi ni modification")
    parser.add_argument("--all",      action="store_true",
                        help="Force le renvoi a tous (meme deja notifies)")
    parser.add_argument("--email",    type=str, default=None,
                        help="Cibler un seul candidat par email")
    args = parser.parse_args()

    asyncio.run(main(
        dry_run      = args.dry_run,
        force_all    = args.all,
        filter_email = args.email,
    ))
