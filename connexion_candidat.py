"""
connexion_candidat.py -- Affiche les informations de connexion d'un candidat
(collection "responses", celle utilisee par suivi.py).

Execution : python connexion_candidat.py "nom ou partie du nom"

ATTENTION : le mot de passe est hache (bcrypt) en base -- il est donc
impossible de le retrouver en clair. Ce script affiche les informations de
connexion connues (identifiant public_id, email, statut) et propose, sur
confirmation explicite, de generer un NOUVEAU mot de passe provisoire (meme
mecanisme que "mot de passe oublie") afin de le communiquer au candidat.
"""

import asyncio
import os
import sys
import secrets

import certifi
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


def hash_password(password: str) -> str:
    """Meme algorithme que utils.security.get_password_hash (bcrypt natif)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def main():
    if len(sys.argv) < 2:
        print('\nUsage : python connexion_candidat.py "nom du candidat"\n')
        return

    query = " ".join(sys.argv[1:]).strip().lower()

    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=certifi.where())
    db = client[os.getenv("DATABASE_NAME", "irisq_db")]
    collection = db["responses"]

    candidats = await collection.find({}).to_list(1000)
    matches = [c for c in candidats if query in (c.get("name") or "").lower()]

    if not matches:
        print(f"\nAucun candidat trouve pour '{query}'.\n")
        client.close()
        return

    print()
    print("=" * 90)
    print(f"  INFORMATIONS DE CONNEXION  -  {len(matches)} resultat(s) pour '{query}'")
    print("=" * 90)

    for c in matches:
        answers = c.get("answers") or {}
        certification = (
            answers.get("Certification souhaitée")
            or answers.get("Certification souhaitee")
            or "N/A"
        )
        public_id   = c.get("public_id", "N/A")
        email       = c.get("email", "N/A")
        status      = c.get("status", "pending")
        must_change = c.get("must_change_password", False)
        blocked     = c.get("credentials_blocked", False)
        exam_token  = c.get("exam_token")

        print(f"\n  Nom            : {c.get('name', 'N/A')}")
        print(f"  Formation      : {certification}")
        print(f"  Identifiant    : {public_id}")
        print(f"  Email          : {email}")
        print(f"  Statut dossier : {status}")
        print(f"  Mot de passe   : (hache - non recuperable en clair)")
        print(f"  Doit changer   : {'Oui' if must_change else 'Non'}")
        print(f"  Bloque         : {'Oui' if blocked else 'Non'}")
        if exam_token:
            frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
            if frontend_url:
                print(f"  Lien examen    : {frontend_url}/examen/{exam_token}")
            else:
                print(f"  Token examen   : {exam_token}")

    print()
    print("=" * 90)

    if len(matches) > 1:
        print("\n  Plusieurs candidats correspondent -- affinez la recherche pour reinitialiser un mot de passe.\n")
        client.close()
        return

    candidat = matches[0]
    public_id = candidat.get("public_id")
    if not public_id:
        client.close()
        return

    reponse = input(
        f"\n  Voulez-vous generer un NOUVEAU mot de passe provisoire pour '{candidat.get('name')}' "
        f"(public_id={public_id}) ? (tapez 'OUI' pour confirmer) : "
    ).strip()

    if reponse != "OUI":
        print("\n  Aucune modification effectuee.\n")
        client.close()
        return

    new_password = secrets.token_urlsafe(6)[:8]
    new_hash = hash_password(new_password)

    result = await collection.update_many(
        {"public_id": public_id},
        {"$set": {
            "password_hash": new_hash,
            "must_change_password": True,
        }},
    )

    print()
    print("=" * 90)
    print(f"  OK - Nouveau mot de passe genere pour {result.modified_count} dossier(s) lie(s) a {public_id} :")
    print(f"     Identifiant   : {public_id}")
    print(f"     Mot de passe  : {new_password}")
    print("     (Le candidat devra le changer a sa premiere connexion.)")
    print("=" * 90)
    print()

    client.close()


asyncio.run(main())
