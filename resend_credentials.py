"""
resend_credentials.py
---------------------
Envoie (ou re-envoie) les identifiants de connexion a tous les candidats
qui ont postule mais n'ont pas recu leur email de confirmation.

Le script :
  1. Charge tous les dossiers depuis MongoDB
  2. Regroupe par public_id (un seul email par candidat)
  3. Genere un nouveau mot de passe temporaire pour chacun
  4. Met a jour le password_hash en base
  5. Envoie l'email via Brevo

Usage :
  python resend_credentials.py              -> envoie a TOUS les candidats
  python resend_credentials.py --dry-run    -> affiche la liste sans envoyer
  python resend_credentials.py --email ak@gmail.com  -> un seul candidat
"""

import asyncio
import argparse
import secrets
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import os
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

from email_service import notify_candidate_submission_received

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_ctx.hash(password)


def new_temp_password() -> str:
    """Genere un mot de passe temporaire de 8 caracteres URL-safe."""
    return secrets.token_urlsafe(6)[:8]


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt(label: str, value: str, width: int = 22) -> str:
    return f"  {label:<{width}}: {value}"


# ── Script principal ──────────────────────────────────────────────────────────

async def main(dry_run: bool = False, filter_email: str = None):
    print()
    print("=" * 60)
    print("  IRISQ - Renvoi des identifiants candidats")
    print("=" * 60)

    if not MONGO_URI:
        print("[ERREUR] MONGO_URI non configure dans .env")
        sys.exit(1)

    # ── Connexion MongoDB ──────────────────────────────────────────────────────
    client = AsyncIOMotorClient(MONGO_URI)
    db     = client[DATABASE_NAME]
    print(f"\n[DB] Connecte a {DATABASE_NAME}")

    # ── Recuperation des dossiers ─────────────────────────────────────────────
    query = {
        "public_id": {"$exists": True, "$ne": None, "$ne": ""},
        "email":     {"$exists": True, "$ne": None, "$ne": ""},
    }
    if filter_email:
        query["email"] = filter_email.strip().lower()

    cursor   = db["responses"].find(query).sort("submitted_at", 1)
    all_docs = await cursor.to_list(length=None)

    if not all_docs:
        print("\n[INFO] Aucun dossier trouve avec les criteres donnes.")
        client.close()
        return

    # ── Dedoublonnage : un seul email par public_id ───────────────────────────
    seen: dict = {}
    for doc in all_docs:
        pid = doc.get("public_id", "")
        if pid and pid not in seen:
            seen[pid] = doc

    candidates = list(seen.values())

    print(f"\n[INFO] {len(all_docs)} dossier(s) trouve(s) => {len(candidates)} candidat(s) unique(s)\n")

    if dry_run:
        print("[!] MODE DRY-RUN : aucun email ne sera envoye, aucune modif en base\n")

    print("-" * 60)

    # ── Traitement ────────────────────────────────────────────────────────────
    success_count = 0
    fail_count    = 0
    skip_count    = 0

    for i, doc in enumerate(candidates, 1):
        public_id = doc.get("public_id", "")
        email     = (doc.get("email") or "").strip()
        name      = (doc.get("name")  or "Candidat").strip()

        # Recuperer TOUTES les certifications de ce candidat
        all_certs_cursor = db["responses"].find({"public_id": public_id})
        all_certs_docs   = await all_certs_cursor.to_list(length=None)
        certifications   = list({
            d.get("answers", {}).get("Certification souhaitee", "")
            or d.get("answers", {}).get("Certification souhait\xe9e", "")
            for d in all_certs_docs
        } - {""})
        if not certifications:
            # fallback: chercher la cle exacte avec accent
            certifications = list({
                d.get("answers", {}).get("Certification souhaitée", "")
                for d in all_certs_docs
            } - {""})
        if not certifications:
            certifications = ["Non specifiee"]

        print(f"[{i}/{len(candidates)}] {name}")
        print(fmt("Email",    email))
        print(fmt("Public ID", public_id))
        print(fmt("Certification(s)", ", ".join(certifications)))

        if not email:
            print("  [IGNORE] Pas d'adresse email\n")
            skip_count += 1
            continue

        if dry_run:
            print("  [DRY-RUN] Email non envoye\n")
            continue

        # Generer un nouveau mot de passe temporaire
        temp_password = new_temp_password()
        new_hash      = get_password_hash(temp_password)

        # Mettre a jour le mot de passe dans TOUS les dossiers de ce candidat
        await db["responses"].update_many(
            {"public_id": public_id},
            {"$set": {
                "password_hash":         new_hash,
                "must_change_password":  True,
                "credentials_resent_at": datetime.utcnow(),
            }}
        )

        # Envoyer l'email
        ok = notify_candidate_submission_received(
            to_email         = email,
            candidate_name   = name,
            public_id        = public_id,
            certifications   = certifications,
            default_password = temp_password,
        )

        if ok:
            print(f"  [OK] Email envoye  (nouveau mdp : {temp_password})\n")
            success_count += 1
        else:
            print("  [ECHEC] Envoi echoue - verifier logs Brevo\n")
            fail_count += 1

    # ── Resume ────────────────────────────────────────────────────────────────
    print("=" * 60)
    print("  RESUME")
    print("=" * 60)
    if dry_run:
        print(f"  Candidats trouves     : {len(candidates)}")
        print(f"  Ignores (sans email)  : {skip_count}")
        print("  [!] Dry-run : aucun email envoye, aucune base modifiee")
    else:
        print(f"  [OK]    Envoyes avec succes : {success_count}")
        print(f"  [ECHEC] Echecs              : {fail_count}")
        print(f"  [IGN]   Ignores             : {skip_count}")
        print(f"          Total traites       : {len(candidates)}")
    print("=" * 60)
    print()

    client.close()


# ── Point d'entree ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Renvoie les identifiants de connexion aux candidats IRISQ"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche la liste des candidats sans envoyer d'email ni modifier la base",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Restreindre l'envoi a un seul candidat (par adresse email)",
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run, filter_email=args.email))
