"""
delete_and_reinvite.py
----------------------
Supprime les candidatures d'un candidat et lui envoie un email
d'excuse l'invitant a se recandidater.

Usage :
  python delete_and_reinvite.py --dry-run     -> apercu sans rien modifier
  python delete_and_reinvite.py               -> supprime + envoie l'email
"""

import asyncio
import argparse
import sys
import os
import certifi

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from email_service import send_email, FRONTEND_URL

# ── Candidat cible ────────────────────────────────────────────────────────────
TARGET_EMAIL = "antandiaye@pna.sn"
TARGET_NAME  = "Anta Ndiaye"
# ─────────────────────────────────────────────────────────────────────────────

MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")


def build_reinvite_email(name: str, certifications: list) -> str:
    cert_items = "".join(
        f'<li style="margin-bottom:6px;color:#1a237e;font-weight:600;">{c}</li>'
        for c in certifications
    )
    cert_list_html = f"""
        <ul style="list-style:none;padding:12px 20px;margin:0 0 20px 0;
                   background:#f0f4ff;border-radius:10px;border-left:4px solid #1a237e;">
            {cert_items}
        </ul>
    """ if certifications else ""

    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:0 auto;
                background:#f4f6f9;padding:32px 16px;">

        <div style="text-align:center;margin-bottom:28px;">
            <div style="color:#1a237e;font-weight:800;font-size:12px;
                        letter-spacing:0.25em;text-transform:uppercase;">
                IRISQ-CERTIFICATION
            </div>
        </div>

        <div style="background:white;border-radius:16px;padding:32px;
                    border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,.06);">

            <!-- Bloc excuses -->
            <div style="background:#fff8f1;border-left:4px solid #f97316;
                        border-radius:0 10px 10px 0;padding:16px 18px;margin-bottom:28px;">
                <p style="color:#9a3412;font-size:14px;margin:0 0 6px 0;
                           font-weight:700;">Toutes nos excuses</p>
                <p style="color:#9a3412;font-size:14px;margin:0;line-height:1.7;">
                    Bonjour <strong>{name}</strong>, nous avons rencontre un probleme
                    technique sur notre plateforme qui a affecte votre dossier de candidature.
                    Nous nous excusons sincerement pour la gene occasionnee.
                </p>
            </div>

            <h2 style="color:#1a237e;font-size:20px;font-weight:800;
                       text-align:center;margin:0 0 16px 0;">
                Invitation a vous recandidater
            </h2>

            <p style="color:#475569;font-size:14px;line-height:1.7;
                      text-align:center;margin:0 0 20px 0;">
                Suite a ce probleme, votre candidature pour la (les) formation(s)
                suivante(s) a ete reinitialise(e) :
            </p>

            {cert_list_html}

            <p style="color:#475569;font-size:14px;line-height:1.7;
                      text-align:center;margin:0 0 28px 0;">
                Vous pouvez desormais soumettre a nouveau votre candidature via
                notre formulaire en ligne. Vous recevrez immediatement un email
                de confirmation avec vos nouveaux identifiants de connexion.
            </p>

            <div style="height:1px;background:#e2e8f0;margin-bottom:24px;"></div>

            <!-- Bloc informatif -->
            <div style="background:#e8f5e9;border-left:4px solid #2e7d32;
                        border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:28px;">
                <p style="color:#1b5e20;font-size:14px;margin:0;line-height:1.6;">
                    <strong>Bon a savoir :</strong> Des que vous soumettez votre candidature,
                    un email avec vos identifiants vous est envoye automatiquement
                    et instantanement.
                </p>
            </div>

            <div style="text-align:center;">
                <a href="{FRONTEND_URL}/demande-certification"
                   style="display:inline-block;background:#1a237e;color:white;
                          padding:14px 40px;border-radius:10px;text-decoration:none;
                          font-size:14px;font-weight:700;letter-spacing:0.03em;">
                    Soumettre ma candidature
                </a>
            </div>

            <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:20px;">
                Si vous avez des questions, contactez-nous directement en repondant
                a cet email.
            </p>
        </div>

        <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:20px;">
            &copy; IRISQ &mdash; Institut des Risques &amp; de la Qualite
        </p>
    </div>
    """


async def main(dry_run: bool):
    print()
    print("=" * 60)
    print("  IRISQ - Suppression + Invitation a recandidater")
    print("=" * 60)

    if not MONGO_URI:
        print("[ERREUR] MONGO_URI non configure dans .env")
        sys.exit(1)

    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]
    print(f"\n[DB] Connecte a {DATABASE_NAME}")

    # ── Recherche des dossiers du candidat ────────────────────────────────────
    docs = await db["responses"].find({"email": TARGET_EMAIL}).to_list(length=None)

    if not docs:
        print(f"\n[INFO] Aucun dossier trouve pour {TARGET_EMAIL}")
        client.close()
        return

    public_id = docs[0].get("public_id", "N/A")
    certifications = [
        d.get("answers", {}).get("Certification souhait\xe9e", "")
        or d.get("answers", {}).get("Certification souhaitee", "")
        for d in docs
    ]
    certifications = [c for c in certifications if c]

    print(f"\n  Candidat  : {TARGET_NAME}")
    print(f"  Email     : {TARGET_EMAIL}")
    print(f"  Public ID : {public_id}")
    print(f"  Dossiers  : {len(docs)}")
    for c in certifications:
        print(f"    - {c}")

    if dry_run:
        print("\n[!] MODE DRY-RUN : aucune suppression, aucun email\n")
        client.close()
        return

    print()

    # ── Confirmation manuelle ─────────────────────────────────────────────────
    confirm = input(f"Confirmer la suppression des {len(docs)} dossier(s) et l'envoi de l'email ? [oui/non] : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("\nAnnule.")
        client.close()
        return

    # ── Suppression des dossiers ──────────────────────────────────────────────
    result = await db["responses"].delete_many({"email": TARGET_EMAIL})
    print(f"\n[OK] {result.deleted_count} dossier(s) supprime(s)")

    # ── Verifier et supprimer le compte candidat si existant ─────────────────
    acc = await db["candidate_accounts"].find_one({"email": TARGET_EMAIL})
    if acc:
        await db["candidate_accounts"].delete_one({"email": TARGET_EMAIL})
        print("[OK] Compte candidat supprime")
    else:
        print("[INFO] Pas de compte candidat separe a supprimer")

    # ── Envoi de l'email ──────────────────────────────────────────────────────
    subject    = "Invitation a recandidater — IRISQ Certification"
    html_body  = build_reinvite_email(TARGET_NAME, certifications)

    ok = send_email(TARGET_EMAIL, subject, html_body)
    if ok:
        print(f"[OK] Email d'invitation envoye a {TARGET_EMAIL}")
    else:
        print(f"[ECHEC] Email non envoye a {TARGET_EMAIL} - verifier Brevo")

    print()
    print("=" * 60)
    print("  RESUME")
    print("=" * 60)
    print(f"  Dossiers supprimes : {result.deleted_count}")
    print(f"  Email envoye       : {'Oui' if ok else 'Non - ECHEC'}")
    print("=" * 60)
    print()

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Supprime les candidatures d'Anta Ndiaye et envoie un email d'invitation"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apercu sans suppression ni email",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
