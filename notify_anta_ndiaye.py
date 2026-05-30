"""
notify_anta_ndiaye.py — Informe Anta Ndiaye que le probleme est resolu
et lui envoie ses identifiants pour tester la connexion et l'examen.
Execution : python notify_anta_ndiaye.py
"""

import asyncio
import os
import sys
import certifi
sys.path.insert(0, os.path.dirname(__file__))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from email_service import send_email, FRONTEND_URL

load_dotenv()

PUBLIC_ID = "IC26D01L-0010"

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=certifi.where())
    db = client[os.getenv("DATABASE_NAME", "irisq_db")]

    # Recuperer le dossier valide (approved)
    doc = await db["responses"].find_one({"public_id": PUBLIC_ID, "status": "approved"})
    if not doc:
        print("Dossier approuve non trouve, on prend le premier dossier disponible.")
        doc = await db["responses"].find_one({"public_id": PUBLIC_ID})

    if not doc:
        print("Aucun dossier trouve pour", PUBLIC_ID)
        client.close()
        return

    email   = doc.get("email", "")
    name    = doc.get("name", "Candidat")
    answers = doc.get("answers") or {}
    certification = answers.get("Certification souhaitée") or answers.get("Certification souhaitee", "Certification IRISQ")

    print(f"Candidat  : {name}")
    print(f"Email     : {email}")
    print(f"Formation : {certification}")
    print(f"Statut    : {doc.get('status')}")
    print(f"ID Public : {PUBLIC_ID}")
    print()

    html = """
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:0 auto;background:#f4f6f9;padding:32px 16px;">

        <!-- En-tete -->
        <div style="text-align:center;margin-bottom:28px;">
            <img src=\"""" + FRONTEND_URL + """/logo.png\" alt="IRISQ" width="72" height="72"
                 style="border-radius:50%;border:3px solid #2e7d32;padding:4px;background:white;" />
            <div style="color:#1a237e;font-weight:800;font-size:12px;letter-spacing:0.25em;
                        text-transform:uppercase;margin-top:8px;">IRISQ-CERTIFICATION</div>
        </div>

        <!-- Carte principale -->
        <div style="background:white;border-radius:16px;padding:32px;border:1px solid #e2e8f0;
                    box-shadow:0 2px 8px rgba(0,0,0,0.06);">

            <!-- Icone OK -->
            <div style="text-align:center;margin-bottom:20px;">
                <div style="display:inline-flex;align-items:center;justify-content:center;
                            width:60px;height:60px;background:#e8f5e9;border-radius:50%;font-size:28px;">
                    &#10003;
                </div>
            </div>

            <h2 style="color:#1a237e;font-size:20px;font-weight:800;text-align:center;margin:0 0 12px 0;">
                Probleme resolu — Vous pouvez vous connecter
            </h2>

            <p style="color:#475569;font-size:14px;line-height:1.7;text-align:center;margin:0 0 24px 0;">
                Bonjour <strong>""" + name + """</strong>,<br>
                Nous vous informons que le probleme technique qui vous empechait
                de vous connecter a votre espace candidat est desormais resolu.<br><br>
                Votre dossier de candidature pour <strong>""" + certification + """</strong>
                a bien ete valide. Vous pouvez maintenant vous connecter et acceder
                a votre session d'examen.
            </p>

            <!-- Statut -->
            <div style="background:#e8f5e9;border-left:4px solid #2e7d32;border-radius:0 8px 8px 0;
                        padding:14px 20px;margin-bottom:24px;">
                <p style="margin:0;font-size:12px;color:#2e7d32;font-weight:700;text-transform:uppercase;">
                    Statut de votre dossier</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:800;color:#1b5e20;">
                    Valide — Examen disponible</p>
            </div>

            <div style="height:1px;background:#e2e8f0;margin-bottom:24px;"></div>

            <!-- Identifiants -->
            <p style="color:#1a237e;font-size:13px;font-weight:700;text-transform:uppercase;
                      letter-spacing:0.08em;margin:0 0 12px 0;">Vos identifiants de connexion</p>

            <table style="width:100%;font-size:14px;border-collapse:collapse;
                          background:#f8fafc;border-radius:10px;overflow:hidden;">
                <tr>
                    <td style="padding:12px 16px;color:#64748b;font-weight:600;
                               border-bottom:1px solid #e2e8f0;">Identifiant</td>
                    <td style="padding:12px 16px;color:#1a237e;font-weight:700;
                               font-family:monospace;font-size:16px;text-align:right;
                               border-bottom:1px solid #e2e8f0;">""" + PUBLIC_ID + """</td>
                </tr>
                <tr>
                    <td style="padding:12px 16px;color:#64748b;font-weight:600;">Mot de passe</td>
                    <td style="padding:12px 16px;color:#1a237e;font-weight:700;
                               font-family:monospace;font-size:16px;text-align:right;">Md6WkTiW</td>
                </tr>
            </table>

            <div style="background:#fff8f1;border-left:4px solid #f97316;padding:14px;
                        border-radius:0 8px 8px 0;margin-top:16px;margin-bottom:28px;">
                <p style="color:#9a3412;font-size:13px;margin:0;line-height:1.5;">
                    Lors de votre premiere connexion, il vous sera demande de
                    definir un nouveau mot de passe personnel.
                </p>
            </div>

            <!-- Bouton -->
            <div style="text-align:center;">
                <a href=\"""" + FRONTEND_URL + """/candidat/login\"
                   style="display:inline-block;background:#1a237e;color:white;
                          padding:14px 40px;border-radius:10px;text-decoration:none;
                          font-size:15px;font-weight:700;letter-spacing:0.03em;
                          box-shadow:0 4px 12px rgba(26,35,126,0.25);">
                    Acceder a mon espace et passer l'examen
                </a>
            </div>
        </div>

        <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:20px;">
            IRISQ — Institut des Risques et de la Qualite<br>
            Pour toute question, contactez-nous a l'adresse de votre centre de formation.
        </p>
    </div>
    """

    print("Tapez 'ENVOYER' pour confirmer l'envoi : ", end="")
    confirm = input().strip()
    if confirm != "ENVOYER":
        print("[x] Annule.")
        client.close()
        return

    subject = "Votre acces est retabli — " + certification + " — IRISQ"
    ok = send_email(email, subject, html)
    print(f"Email envoye a {email} : {'OK' if ok else 'ECHEC'}")
    client.close()

asyncio.run(main())
