"""
fix_anta_ndiaye.py — Synchronise le mot de passe sur les 2 dossiers d'Anta Ndiaye
et renvoie un email avec les bons identifiants.
"""
import asyncio
import os
import secrets
import sys
import certifi
sys.path.insert(0, os.path.dirname(__file__))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from utils.security import get_password_hash
from email_service import send_email, FRONTEND_URL

load_dotenv()

PUBLIC_ID = "IC26D01L-0010"

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=certifi.where())
    db = client[os.getenv("DATABASE_NAME", "irisq_db")]

    docs = await db["responses"].find({"public_id": PUBLIC_ID}).to_list(10)
    print(f"Dossiers trouves pour {PUBLIC_ID} : {len(docs)}")
    for d in docs:
        answers = d.get("answers") or {}
        cert = answers.get("Certification souhaitee") or answers.get("Certification souhaitée", "N/A")
        print(f"  - {d.get('name')} | {cert} | statut={d.get('status')}")

    if not docs:
        print("Aucun dossier trouve.")
        client.close()
        return

    # Generer UN seul mot de passe pour les 2 dossiers
    new_password = secrets.token_urlsafe(6)[:8]
    new_hash = get_password_hash(new_password)

    result = await db["responses"].update_many(
        {"public_id": PUBLIC_ID},
        {"$set": {"password_hash": new_hash, "must_change_password": True}}
    )
    print(f"Mot de passe synchronise sur {result.modified_count} dossier(s)")

    # Envoyer l'email
    email = docs[0].get("email", "")
    name  = docs[0].get("name", "Candidat")

    html = """
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:0 auto;background:#f4f6f9;padding:32px 16px;">
        <div style="text-align:center;margin-bottom:24px;">
            <div style="color:#1a237e;font-weight:800;font-size:12px;letter-spacing:0.25em;text-transform:uppercase;">IRISQ-CERTIFICATION</div>
        </div>
        <div style="background:white;border-radius:16px;padding:32px;border:1px solid #e2e8f0;">
            <h2 style="color:#1a237e;font-size:20px;font-weight:800;text-align:center;margin:0 0 12px 0;">Vos identifiants de connexion</h2>
            <p style="color:#475569;font-size:14px;line-height:1.7;text-align:center;margin:0 0 24px 0;">
                Bonjour <strong>""" + name + """</strong>,<br>
                Suite a un incident technique, voici vos identifiants mis a jour.<br>
                Utilisez-les pour acceder a votre espace candidat et suivre vos dossiers.
            </p>
            <table style="width:100%;font-size:14px;border-collapse:collapse;background:#f8fafc;border-radius:10px;overflow:hidden;">
                <tr>
                    <td style="padding:12px 16px;color:#64748b;font-weight:600;border-bottom:1px solid #e2e8f0;">Identifiant</td>
                    <td style="padding:12px 16px;color:#1a237e;font-weight:700;font-family:monospace;text-align:right;border-bottom:1px solid #e2e8f0;">""" + PUBLIC_ID + """</td>
                </tr>
                <tr>
                    <td style="padding:12px 16px;color:#64748b;font-weight:600;">Mot de passe provisoire</td>
                    <td style="padding:12px 16px;color:#1a237e;font-weight:700;font-family:monospace;text-align:right;">""" + new_password + """</td>
                </tr>
            </table>
            <div style="background:#fff8f1;border-left:4px solid #f97316;padding:14px;border-radius:0 8px 8px 0;margin-top:20px;margin-bottom:24px;">
                <p style="color:#9a3412;font-size:13px;margin:0;line-height:1.5;">
                    Lors de votre premiere connexion, il vous sera demande de definir un nouveau mot de passe personnel.
                </p>
            </div>
            <div style="text-align:center;">
                <a href=\"""" + FRONTEND_URL + """/candidat/login\" style="display:inline-block;background:#1a237e;color:white;padding:13px 36px;border-radius:10px;text-decoration:none;font-size:14px;font-weight:700;">
                    Acceder a mon espace
                </a>
            </div>
        </div>
        <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:20px;">
            IRISQ - Institut des Risques et de la Qualite
        </p>
    </div>
    """

    ok = send_email(email, "Vos identifiants IRISQ - " + PUBLIC_ID, html)
    print(f"Email envoye a {email} : {'OK' if ok else 'ECHEC'}")
    print(f"Nouveau mot de passe : {new_password}")
    client.close()

asyncio.run(main())
