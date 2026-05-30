"""
send_welcome_emails.py
----------------------
Envoie un email de rappel a tous les candidats existants.

Deux cas distingues :
  - must_change_password = True  => jamais connecte => nouveau mot de passe temporaire + identifiants
  - must_change_password = False => deja connecte   => simple rappel sans toucher au mot de passe

Execution : python send_welcome_emails.py
"""

import asyncio
import os
import secrets
import sys
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from utils.security import get_password_hash
from email_service import send_email, FRONTEND_URL

MONGO_URI     = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")

STATUS_LABELS = {
    "pending" : "En attente de validation",
    "approved": "Dossier valide - en cours d evaluation",
    "rejected": "Dossier refuse",
}


def email_nouveaux_identifiants(name: str, public_id: str, password: str, certification: str, status: str) -> str:
    """Email pour les candidats qui n'ont jamais pu se connecter — inclut les identifiants."""
    status_label = STATUS_LABELS.get(status, status)
    status_color = "#f97316" if status == "pending" else "#10b981" if status == "approved" else "#ef4444"

    return f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto;
                background: #f4f6f9; padding: 32px 16px;">

        <div style="text-align: center; margin-bottom: 28px;">
            <img src="{FRONTEND_URL}/logo.png" alt="IRISQ" width="72" height="72"
                 style="border-radius: 50%; border: 3px solid #2e7d32; padding: 4px; background: white;" />
            <div style="color: #1a237e; font-weight: 800; font-size: 12px; letter-spacing: 0.25em;
                        text-transform: uppercase; margin-top: 8px;">IRISQ-CERTIFICATION</div>
        </div>

        <div style="background: white; border-radius: 16px; padding: 32px;
                    border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">

            <h2 style="color: #1a237e; font-size: 20px; font-weight: 800; text-align: center; margin: 0 0 12px 0;">
                Votre espace candidat est actif
            </h2>

            <p style="color: #475569; font-size: 14px; line-height: 1.7; text-align: center; margin: 0 0 20px 0;">
                Bonjour <strong>{name}</strong>,<br>
                Votre candidature pour <strong>{certification}</strong> a bien ete enregistree.<br>
                En raison d'un incident technique sur notre systeme d'email, vous n'aviez pas
                encore recu vos identifiants de connexion. Les voici.
            </p>

            <!-- Statut -->
            <div style="background: #f8fafc; border-radius: 10px; padding: 14px 20px;
                        margin-bottom: 24px; border-left: 4px solid {status_color};">
                <p style="margin: 0; font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase;">
                    Statut actuel de votre dossier</p>
                <p style="margin: 4px 0 0 0; font-size: 15px; font-weight: 800; color: {status_color};">
                    {status_label}</p>
            </div>

            <div style="height: 1px; background: #e2e8f0; margin-bottom: 24px;"></div>

            <p style="color: #1a237e; font-size: 13px; font-weight: 700; text-transform: uppercase;
                      letter-spacing: 0.08em; margin: 0 0 12px 0;">Vos identifiants de connexion</p>

            <table style="width: 100%; font-size: 14px; border-collapse: collapse;
                          background: #f8fafc; border-radius: 10px; overflow: hidden;">
                <tr>
                    <td style="padding: 12px 16px; color: #64748b; font-weight: 600;
                               border-bottom: 1px solid #e2e8f0;">Identifiant</td>
                    <td style="padding: 12px 16px; color: #1a237e; font-weight: 700;
                               font-family: monospace; text-align: right;
                               border-bottom: 1px solid #e2e8f0;">{public_id}</td>
                </tr>
                <tr>
                    <td style="padding: 12px 16px; color: #64748b; font-weight: 600;">
                        Mot de passe provisoire</td>
                    <td style="padding: 12px 16px; color: #1a237e; font-weight: 700;
                               font-family: monospace; text-align: right;">{password}</td>
                </tr>
            </table>

            <div style="background: #fff8f1; border-left: 4px solid #f97316; padding: 14px;
                        border-radius: 0 8px 8px 0; margin-top: 20px; margin-bottom: 24px;">
                <p style="color: #9a3412; font-size: 13px; margin: 0; line-height: 1.5;">
                    Lors de votre premiere connexion, il vous sera demande de definir un
                    nouveau mot de passe personnel.
                </p>
            </div>

            <div style="text-align: center;">
                <a href="{FRONTEND_URL}/candidat/login"
                   style="display: inline-block; background: #1a237e; color: white;
                          padding: 13px 36px; border-radius: 10px; text-decoration: none;
                          font-size: 14px; font-weight: 700;">
                    Acceder a mon espace
                </a>
            </div>
        </div>

        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 20px;">
            IRISQ — Institut des Risques &amp; de la Qualite
        </p>
    </div>
    """


def email_rappel_simple(name: str, public_id: str, certification: str, status: str) -> str:
    """Email pour les candidats qui se sont deja connectes — pas de nouveau mot de passe."""
    status_label = STATUS_LABELS.get(status, status)
    status_color = "#f97316" if status == "pending" else "#10b981" if status == "approved" else "#ef4444"

    return f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto;
                background: #f4f6f9; padding: 32px 16px;">

        <div style="text-align: center; margin-bottom: 28px;">
            <img src="{FRONTEND_URL}/logo.png" alt="IRISQ" width="72" height="72"
                 style="border-radius: 50%; border: 3px solid #2e7d32; padding: 4px; background: white;" />
            <div style="color: #1a237e; font-weight: 800; font-size: 12px; letter-spacing: 0.25em;
                        text-transform: uppercase; margin-top: 8px;">IRISQ-CERTIFICATION</div>
        </div>

        <div style="background: white; border-radius: 16px; padding: 32px;
                    border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">

            <h2 style="color: #1a237e; font-size: 20px; font-weight: 800; text-align: center; margin: 0 0 12px 0;">
                Rappel — Suivi de votre candidature
            </h2>

            <p style="color: #475569; font-size: 14px; line-height: 1.7; text-align: center; margin: 0 0 20px 0;">
                Bonjour <strong>{name}</strong>,<br>
                Nous vous rappelons que votre candidature pour <strong>{certification}</strong>
                est bien enregistree. Connectez-vous a votre espace pour suivre son evolution.
            </p>

            <!-- Statut -->
            <div style="background: #f8fafc; border-radius: 10px; padding: 14px 20px;
                        margin-bottom: 24px; border-left: 4px solid {status_color};">
                <p style="margin: 0; font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase;">
                    Statut actuel de votre dossier</p>
                <p style="margin: 4px 0 0 0; font-size: 15px; font-weight: 800; color: {status_color};">
                    {status_label}</p>
            </div>

            <!-- ID rappel -->
            <div style="background: #eef2ff; border-radius: 10px; padding: 14px 20px; margin-bottom: 24px;">
                <p style="margin: 0; font-size: 12px; color: #64748b; font-weight: 600;">Votre identifiant</p>
                <p style="margin: 4px 0 0 0; font-size: 18px; font-weight: 800;
                          color: #1a237e; font-family: monospace;">{public_id}</p>
            </div>

            <div style="text-align: center;">
                <a href="{FRONTEND_URL}/candidat/login"
                   style="display: inline-block; background: #1a237e; color: white;
                          padding: 13px 36px; border-radius: 10px; text-decoration: none;
                          font-size: 14px; font-weight: 700;">
                    Suivre mon dossier
                </a>
            </div>
        </div>

        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 20px;">
            IRISQ — Institut des Risques &amp; de la Qualite
        </p>
    </div>
    """


async def main():
    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db = client[DATABASE_NAME]

    candidates = await db["responses"].find(
        {"email": {"$exists": True, "$ne": ""}}
    ).to_list(1000)

    print("=" * 60)
    print("ENVOI EMAILS DE RAPPEL — CANDIDATS EXISTANTS")
    print("=" * 60)
    print(f"Total candidats : {len(candidates)}")
    print()

    jamais_connectes = [c for c in candidates if c.get("must_change_password", True)]
    deja_connectes   = [c for c in candidates if not c.get("must_change_password", True)]

    print(f"Jamais connectes (recevront nouveaux identifiants) : {len(jamais_connectes)}")
    for c in jamais_connectes:
        print(f"    - {c.get('name','N/A'):<30} | {c.get('email','N/A')}")

    print()
    print(f"Deja connectes  (recevront un simple rappel)       : {len(deja_connectes)}")
    for c in deja_connectes:
        print(f"    - {c.get('name','N/A'):<30} | {c.get('email','N/A')}")

    print()
    confirm = input("Tapez 'ENVOYER' pour confirmer l'envoi a tous : ").strip()
    if confirm != "ENVOYER":
        print("[x] Annule.")
        client.close()
        return

    print()
    sent = 0
    failed = 0

    # --- Candidats jamais connectes → nouveau mot de passe ---
    for c in jamais_connectes:
        email         = c.get("email", "")
        name          = c.get("name", "Candidat")
        public_id     = c.get("public_id", "")
        status        = c.get("status", "pending")
        answers       = c.get("answers") or {}
        certification = (
            answers.get("Certification souhaitee")
            or answers.get("Certification souhaitée")
            or "Certification IRISQ"
        )

        if not email or not public_id:
            continue

        new_password = secrets.token_urlsafe(6)[:8]
        new_hash     = get_password_hash(new_password)

        await db["responses"].update_one(
            {"_id": c["_id"]},
            {"$set": {"password_hash": new_hash, "must_change_password": True}}
        )
        await db["candidate_accounts"].update_one(
            {"email": {"$regex": f"^{email}$", "$options": "i"}},
            {"$set": {"password_hash": new_hash, "must_change_password": True}}
        )

        html = email_nouveaux_identifiants(name, public_id, new_password, certification, status)
        ok = send_email(email, f"Vos identifiants IRISQ — {public_id}", html)
        tag = "[OK] " if ok else "[ERR]"
        print(f"  {tag} IDENTIFIANTS -> {name} ({email})")
        sent += ok
        failed += not ok

    # --- Candidats deja connectes → simple rappel ---
    for c in deja_connectes:
        email         = c.get("email", "")
        name          = c.get("name", "Candidat")
        public_id     = c.get("public_id", "")
        status        = c.get("status", "pending")
        answers       = c.get("answers") or {}
        certification = (
            answers.get("Certification souhaitee")
            or answers.get("Certification souhaitée")
            or "Certification IRISQ"
        )

        if not email or not public_id:
            continue

        html = email_rappel_simple(name, public_id, certification, status)
        ok = send_email(email, f"Rappel — Suivi de votre candidature IRISQ", html)
        tag = "[OK] " if ok else "[ERR]"
        print(f"  {tag} RAPPEL      -> {name} ({email})")
        sent += ok
        failed += not ok

    print()
    print(f"[DONE] {sent} email(s) envoye(s) avec succes, {failed} echec(s).")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
