import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
RH_EMAIL = os.getenv("RH_EMAIL", "")
EVALUATOR_EMAIL = os.getenv("EVALUATOR_EMAIL", "")


def send_email(to_email: str, subject: str, html_body: str):
    """Send an email via Gmail SMTP."""
    if not SMTP_USER or not SMTP_PASSWORD or SMTP_PASSWORD == "VOTRE_MOT_DE_PASSE_APPLICATION_GOOGLE":
        print(f"[EMAIL] SMTP non configuré — email ignoré vers {to_email}")
        print(f"[EMAIL] Sujet: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"IRISQ Certification <{SMTP_FROM}>"
        msg["To"] = to_email

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())

        print(f"[EMAIL] Email envoyé avec succès à {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Erreur lors de l'envoi au candidat ({to_email}): {e}")
        return False


def notify_rh_new_submission(candidate_id: str, candidate_name: str, certification: str):
    """Notify RH that a new candidate submitted a form."""
    subject = f"Nouvelle candidature — {candidate_id} — {certification}"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc; padding: 32px;">
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="display: inline-block; background: #0f172a; color: white; font-weight: bold; padding: 8px 16px; border-radius: 8px; font-size: 14px; letter-spacing: 0.5px;">
                    IRISQ CERTIFICATION
                </div>
            </div>

            <h2 style="color: #0f172a; font-size: 20px; margin-bottom: 8px; text-align: center;">
                Nouvelle candidature reçue
            </h2>
            <p style="color: #64748b; text-align: center; font-size: 14px; margin-bottom: 24px;">
                Un candidat vient de soumettre sa demande de certification.
            </p>

            <div style="background: #f1f5f9; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600;">ID Candidat</td>
                        <td style="padding: 8px 0; color: #0f172a; font-weight: 700; font-family: monospace; text-align: right;">{candidate_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Nom</td>
                        <td style="padding: 8px 0; color: #0f172a; text-align: right; border-top: 1px solid #e2e8f0;">{candidate_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Certification</td>
                        <td style="padding: 8px 0; color: #0f172a; text-align: right; border-top: 1px solid #e2e8f0;">{certification}</td>
                    </tr>
                </table>
            </div>

            <div style="text-align: center;">
                <a href="{frontend_url}/dashboard/forms" style="display: inline-block; background: #0f172a; color: white; padding: 12px 28px; border-radius: 10px; text-decoration: none; font-size: 14px; font-weight: 600;">
                    Voir sur le Dashboard RH
                </a>
            </div>
        </div>

        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 24px;">
            Cet email a été envoyé automatiquement par IRISQ Certification.
        </p>
    </div>
    """
    send_email(RH_EMAIL, subject, html_body)


def notify_candidate_submission_received(to_email: str, candidate_name: str, public_id: str, certification: str, default_password: str = ""):
    """Notify the candidate that their submission was successfully received."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    subject = f"Votre candidature a été envoyée — {certification}"
    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; background: #f4f6f9; padding: 32px 16px;">

        <!-- Logo -->
        <div style="text-align: center; margin-bottom: 28px;">
            <img src="{frontend_url}/logo.png" alt="IRISQ" width="72" height="72"
                 style="border-radius: 50%; border: 3px solid #2e7d32; padding: 4px; background: white;" />
            <div style="color: #1a237e; font-weight: 800; font-size: 12px; letter-spacing: 0.25em; text-transform: uppercase; margin-top: 8px;">
                IRISQ-CERTIFICATIONS
            </div>
        </div>

        <!-- Carte principale -->
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">

            <!-- Titre -->
            <h2 style="color: #1a237e; font-size: 20px; font-weight: 800; text-align: center; margin: 0 0 12px 0;">
                Candidature envoyée
            </h2>

            <!-- Message -->
            <p style="color: #475569; font-size: 14px; line-height: 1.7; text-align: center; margin: 0 0 28px 0;">
                Bonjour <strong>{candidate_name}</strong>,<br>
                votre candidature pour <strong>{certification}</strong> a bien été reçue.<br>
                Pour suivre l'évolution de votre dossier, connectez-vous à votre espace candidat.
            </p>

            <!-- Séparateur -->
            <div style="height: 1px; background: #e2e8f0; margin-bottom: 24px;"></div>

            <!-- Identifiants de connexion -->
            <p style="color: #1a237e; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 12px 0;">
                Vos informations de connexion
            </p>
            <table style="width: 100%; font-size: 14px; border-collapse: collapse; background: #f8fafc; border-radius: 10px; overflow: hidden;">
                <tr>
                    <td style="padding: 12px 16px; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Identifiant</td>
                    <td style="padding: 12px 16px; color: #1a237e; font-weight: 700; font-family: monospace; text-align: right; border-bottom: 1px solid #e2e8f0;">{public_id}</td>
                </tr>
                <tr>
                    <td style="padding: 12px 16px; color: #64748b; font-weight: 600;">Mot de passe</td>
                    <td style="padding: 12px 16px; color: #1a237e; font-weight: 700; font-family: monospace; text-align: right;">{default_password}</td>
                </tr>
            </table>

            <!-- Bouton -->
            <div style="text-align: center; margin-top: 28px;">
                <a href="{frontend_url}/candidat/login"
                   style="display: inline-block; background: #1a237e; color: white; padding: 13px 36px; border-radius: 10px; text-decoration: none; font-size: 14px; font-weight: 700; letter-spacing: 0.03em;">
                    Accéder à mon espace
                </a>
            </div>
        </div>

        <!-- Footer -->
        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 20px;">
            © IRISQ — Institut des Risques &amp; de la Qualité
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)


def notify_candidate_status_update(to_email: str, public_id: str, status: str, certification: str, reason: str = None):
    """Notify candidate about their application status update.

    If status == "rejected" and a ``reason`` is provided, it is included in the email.
    """
    status_text = "Approuvée" if status == "approved" else "Refusée"
    status_color = "#10b981" if status == "approved" else "#ef4444"

    subject = f"Mise à jour de votre candidature — {public_id}"

    reason_block = ""
    if status == "rejected" and reason and reason.strip():
        reason_block = f"""
            <div style="background: #fff5f5; border-left: 4px solid #ef4444; padding: 16px; margin-bottom: 24px; border-radius: 0 8px 8px 0;">
                <p style="color: #991b1b; font-size: 14px; margin: 0 0 4px 0; font-weight: 700;">Motif du refus</p>
                <p style="color: #991b1b; font-size: 14px; margin: 0; line-height: 1.6; white-space: pre-line;">{reason.strip()}</p>
            </div>
        """
    
    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc; padding: 32px;">
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="display: inline-block; background: #0f172a; color: white; font-weight: bold; padding: 8px 16px; border-radius: 8px; font-size: 14px; letter-spacing: 0.5px;">
                    IRISQ CERTIFICATION
                </div>
            </div>

            <h2 style="color: #0f172a; font-size: 20px; margin-bottom: 8px; text-align: center;">
                Suivi de votre dossier
            </h2>
            <p style="color: #64748b; text-align: center; font-size: 14px; margin-bottom: 24px;">
                Une décision a été prise concernant votre demande de certification.
            </p>

            <div style="background: #f1f5f9; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600;">ID Public</td>
                        <td style="padding: 8px 0; color: #0f172a; font-weight: 700; font-family: monospace; text-align: right;">{public_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Certification</td>
                        <td style="padding: 8px 0; color: #0f172a; text-align: right; border-top: 1px solid #e2e8f0;">{certification}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Statut</td>
                        <td style="padding: 8px 0; color: {status_color}; font-weight: 700; text-align: right; border-top: 1px solid #e2e8f0; text-transform: uppercase;">
                            {status_text}
                        </td>
                    </tr>
                </table>
            </div>

            {reason_block}

            <p style="color: #475569; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
                { "Félicitations ! Votre dossier a été validé par notre équipe RH. Votre candidature est maintenant transmise au jury pour évaluation technique." if status == "approved" else "Nous avons le regret de vous informer que votre dossier n'a pas été retenu après examen par notre équipe RH. Conformément à cette décision, l'accès à votre espace candidat a été désactivé." }
            </p>

            <div style="background: #fff8f1; border-left: 4px solid #f97316; padding: 16px; margin-bottom: 24px; border-radius: 0 8px 8px 0;">
                <p style="color: #9a3412; font-size: 14px; margin: 0; font-weight: 500;">
                    <strong>⚠️ IMPORTANT :</strong> Veuillez conserver précieusement votre <strong>ID Public ({public_id})</strong>. Il vous sera indispensable pour la suite de votre évaluation et pour accéder à vos examens.
                </p>
            </div>

            <div style="text-align: center; margin-top: 32px; padding-top: 24px; border-top: 1px solid #f1f5f9;">
                <p style="color: #94a3b8; font-size: 12px; margin: 0;">
                    Veuillez conserver votre ID Public pour toute communication future.
                </p>
            </div>
        </div>

        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 24px;">
            Cet email a été envoyé automatiquement par IRISQ Certification.
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)

def notify_candidate_exam_link(to_email: str, public_id: str, candidate_name: str, certification: str, candidat_link: str, start_time: str = None):
    """Notify candidate that their technical exam has been scheduled."""
    subject = f"Convocation à l'Examen Technique — {certification}"

    start_time_block = ""
    if start_time:
        start_time_block = f"""
            <tr>
                <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Début de l'épreuve</td>
                <td style="padding: 8px 0; color: #1a237e; text-align: right; border-top: 1px solid #e2e8f0; font-weight: 700;">{start_time}</td>
            </tr>
        """

    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; background: #f4f6f9; padding: 32px 16px;">

        <!-- Logo -->
        <div style="text-align: center; margin-bottom: 28px;">
            <div style="color: #1a237e; font-weight: 800; font-size: 12px; letter-spacing: 0.25em; text-transform: uppercase;">
                IRISQ-CERTIFICATIONS
            </div>
        </div>

        <!-- Carte principale -->
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">

            <h2 style="color: #1a237e; font-size: 20px; font-weight: 800; text-align: center; margin: 0 0 12px 0;">
                Convocation d'Examen
            </h2>
            <p style="color: #475569; font-size: 14px; line-height: 1.7; text-align: center; margin: 0 0 24px 0;">
                Bonjour <strong>{candidate_name}</strong>,<br>
                votre épreuve technique pour la certification <strong>{certification}</strong> a été programmée.<br>
                Connectez-vous à votre espace candidat pour consulter les détails et passer l'examen.
            </p>

            <!-- Infos examen -->
            <div style="background: #f8fafc; border-radius: 12px; padding: 20px; margin-bottom: 24px; border: 1px solid #e2e8f0;">
                <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600;">ID Public</td>
                        <td style="padding: 8px 0; color: #1a237e; font-weight: 700; font-family: monospace; text-align: right;">{public_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Certification</td>
                        <td style="padding: 8px 0; color: #0f172a; text-align: right; border-top: 1px solid #e2e8f0; font-weight: 700;">{certification}</td>
                    </tr>
                    {start_time_block}
                </table>
            </div>

            <!-- Règles -->
            <div style="background: #fff1f2; border-left: 4px solid #e11d48; padding: 16px; margin-bottom: 24px; border-radius: 0 8px 8px 0;">
                <h3 style="color: #be123c; font-size: 14px; margin: 0 0 8px 0; font-weight: bold;">Règles de l'examen :</h3>
                <ul style="color: #9f1239; font-size: 13px; margin: 0; padding-left: 20px; line-height: 1.8;">
                    <li>L'examen se déroule en plein écran obligatoirement.</li>
                    <li>Toute sortie du plein écran ou changement d'onglet sera détecté.</li>
                    <li>Le compte à rebours ne peut pas être mis en pause.</li>
                </ul>
            </div>

            <!-- Bouton -->
            <div style="text-align: center; margin-bottom: 16px;">
                <a href="{candidat_link}" style="display: inline-block; background: #1a237e; color: white; padding: 13px 36px; border-radius: 10px; text-decoration: none; font-size: 14px; font-weight: 700; letter-spacing: 0.03em;">
                    Accéder à mon espace candidat
                </a>
            </div>

            <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 16px;">
                Connectez-vous avec votre <strong>ID Public ({public_id})</strong> et votre mot de passe.
            </p>
        </div>

        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 20px;">
            © IRISQ — Institut des Risques &amp; de la Qualité
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)

def notify_examiner_assignment(to_email: str, candidate_id: str, certification: str):
    """Notify an examiner that a new exam copy has been assigned to them."""
    subject = f"Nouvelle Copie à Corriger — {candidate_id}"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc; padding: 32px;">
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="display: inline-block; background: #1a237e; color: white; font-weight: bold; padding: 8px 16px; border-radius: 8px; font-size: 14px; letter-spacing: 0.5px;">
                    IRISQ CORRECTIONS
                </div>
            </div>

            <h2 style="color: #0f172a; font-size: 20px; margin-bottom: 8px; text-align: center;">
                Nouvelle Assignation
            </h2>
            <p style="color: #64748b; text-align: center; font-size: 14px; margin-bottom: 24px;">
                Bonjour, une nouvelle copie d'examen vous a été assignée pour correction.
            </p>

            <div style="background: #e8eaf6; border-radius: 12px; padding: 20px; margin-bottom: 24px; border: 1px solid #c5cae9;">
                <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #1a237e; font-weight: 600;">ID Candidat</td>
                        <td style="padding: 8px 0; color: #0f172a; font-weight: 700; font-family: monospace; text-align: right;">{candidate_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #1a237e; font-weight: 600; border-top: 1px solid #c5cae9;">Certification</td>
                        <td style="padding: 8px 0; color: #0f172a; text-align: right; border-top: 1px solid #c5cae9; font-weight: bold;">{certification}</td>
                    </tr>
                </table>
            </div>

            <div style="text-align: center; margin-bottom: 16px;">
                <a href="{frontend_url}/evaluateur/corrections" style="display: inline-block; background: #1a237e; color: white; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-size: 16px; font-weight: 600; box-shadow: 0 4px 6px -1px rgba(26, 35, 126, 0.2);">
                    Accéder à mon Espace Corrections
                </a>
            </div>
            
            <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 32px; padding-top: 24px; border-top: 1px solid #f1f5f9;">
                Cet email a été envoyé automatiquement par le portail d'évaluation IRISQ.
            </p>
        </div>
    </div>
    """
    send_email(to_email, subject, html_body)


def notify_candidate_document_issue(to_email: str, candidate_name: str, public_id: str, certification: str, document_name: str, message: str = ""):
    """Ask the candidate to re-upload a specific document that was rejected during validation."""
    subject = f"Document à renvoyer — {document_name} — {public_id}"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    safe_message = (message or "").strip()
    extra_block = ""
    if safe_message:
        extra_block = f"""
            <div style="background: #fff8f1; border-left: 4px solid #f97316; padding: 16px; margin-bottom: 24px; border-radius: 0 8px 8px 0;">
                <p style="color: #9a3412; font-size: 14px; margin: 0 0 4px 0; font-weight: 600;">Message de l'équipe RH :</p>
                <p style="color: #9a3412; font-size: 14px; margin: 0; white-space: pre-line;">{safe_message}</p>
            </div>
        """

    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc; padding: 32px;">
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="display: inline-block; background: #0f172a; color: white; font-weight: bold; padding: 8px 16px; border-radius: 8px; font-size: 14px; letter-spacing: 0.5px;">
                    IRISQ CERTIFICATION
                </div>
            </div>

            <h2 style="color: #0f172a; font-size: 20px; margin-bottom: 8px; text-align: center;">
                Document à renvoyer
            </h2>
            <p style="color: #64748b; text-align: center; font-size: 14px; margin-bottom: 24px;">
                Bonjour {candidate_name}, l'un des documents de votre dossier n'est pas conforme et doit être renvoyé.
            </p>

            <div style="background: #f1f5f9; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600;">ID Public</td>
                        <td style="padding: 8px 0; color: #0f172a; font-weight: 700; font-family: monospace; text-align: right;">{public_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Certification</td>
                        <td style="padding: 8px 0; color: #0f172a; text-align: right; border-top: 1px solid #e2e8f0;">{certification}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-weight: 600; border-top: 1px solid #e2e8f0;">Document concerné</td>
                        <td style="padding: 8px 0; color: #dc2626; text-align: right; border-top: 1px solid #e2e8f0; font-weight: 700;">{document_name}</td>
                    </tr>
                </table>
            </div>

            {extra_block}

            <p style="color: #475569; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
                Merci de bien vouloir renvoyer ce document corrigé en répondant à cet email ou en reprenant contact avec notre équipe. Votre candidature restera en attente tant que le document ne sera pas validé.
            </p>

            <div style="text-align: center;">
                <a href="{frontend_url}/demande-certification" style="display: inline-block; background: #0f172a; color: white; padding: 12px 28px; border-radius: 10px; text-decoration: none; font-size: 14px; font-weight: 600;">
                    Accéder au portail
                </a>
            </div>
        </div>

        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 24px;">
            Cet email a été envoyé automatiquement par IRISQ Certification.
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)


def notify_admin_password_reset(to_email: str, admin_name: str, new_password: str):
    """Send a temporary password to an admin user after a forgot-password request."""
    subject = "Réinitialisation de votre mot de passe administrateur — IRISQ"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; background: #f4f6f9; padding: 32px 16px;">
        <div style="text-align: center; margin-bottom: 28px;">
            <div style="color: #1a237e; font-weight: 800; font-size: 13px; letter-spacing: 0.25em; text-transform: uppercase;">
                IRISQ-CERTIFICATIONS
            </div>
        </div>
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
            <h2 style="color: #1a237e; font-size: 20px; font-weight: 800; text-align: center; margin: 0 0 8px 0;">
                Réinitialisation du mot de passe
            </h2>
            <p style="color: #475569; font-size: 14px; text-align: center; margin: 0 0 28px 0;">
                Bonjour <strong>{admin_name}</strong>, voici votre mot de passe provisoire pour accéder au tableau de bord administrateur.
            </p>
            <div style="background: #eef2ff; border-radius: 10px; padding: 20px; margin-bottom: 24px;">
                <table style="width: 100%; font-size: 14px; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden;">
                    <tr>
                        <td style="padding: 12px 16px; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Email</td>
                        <td style="padding: 12px 16px; color: #1a237e; font-weight: 700; font-family: monospace; text-align: right; border-bottom: 1px solid #e2e8f0;">{to_email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 16px; color: #64748b; font-weight: 600;">Mot de passe provisoire</td>
                        <td style="padding: 12px 16px; color: #1a237e; font-weight: 700; font-family: monospace; font-size: 16px; text-align: right;">{new_password}</td>
                    </tr>
                </table>
                <p style="color: #64748b; font-size: 12px; margin: 12px 0 0 0; line-height: 1.5;">
                    Connectez-vous avec ce mot de passe et changez-le immédiatement après votre prochaine connexion.
                </p>
            </div>
            <div style="text-align: center; margin-bottom: 20px;">
                <a href="{frontend_url}/login" style="display: inline-block; background: #1a237e; color: white; padding: 13px 36px; border-radius: 10px; text-decoration: none; font-size: 14px; font-weight: 700;">
                    Accéder au tableau de bord
                </a>
            </div>
            <div style="background: #fff8f1; border-left: 4px solid #f97316; padding: 14px; border-radius: 0 8px 8px 0;">
                <p style="color: #9a3412; font-size: 13px; margin: 0; line-height: 1.5;">
                    Si vous n'êtes pas à l'origine de cette demande, contactez immédiatement l'administrateur système.
                </p>
            </div>
        </div>
        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 20px;">
            © IRISQ — Institut des Risques &amp; de la Qualité
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)


def notify_correcteur_assignment(to_email: str, full_name: str, password: str, candidate_count: int):
    """Envoie les identifiants de connexion au correcteur lors de sa première assignation."""
    subject = "Vos accès correcteur — IRISQ Certifications"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    html_body = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:0 auto;background:#f4f6f9;padding:32px 16px;">
        <div style="text-align:center;margin-bottom:28px;">
            <img src="{frontend_url}/logo.png" alt="IRISQ" width="64" height="64"
                 style="border-radius:50%;border:3px solid #2e7d32;padding:4px;background:white;"/>
            <div style="color:#1a237e;font-weight:800;font-size:12px;letter-spacing:0.25em;text-transform:uppercase;margin-top:8px;">
                IRISQ-CERTIFICATIONS
            </div>
        </div>
        <div style="background:white;border-radius:16px;padding:32px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,.06);">
            <h2 style="color:#1a237e;font-size:20px;font-weight:800;text-align:center;margin:0 0 8px;">
                Assignation de copies
            </h2>
            <p style="color:#475569;font-size:14px;line-height:1.7;text-align:center;margin:0 0 24px;">
                Bonjour <strong>{full_name}</strong>,<br>
                <strong>{candidate_count} copie(s)</strong> vous ont été assignées pour correction.<br>
                Veuillez vous connecter pour accéder à votre espace de correction.
            </p>
            <div style="height:1px;background:#e2e8f0;margin-bottom:24px;"></div>
            <p style="color:#1a237e;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px;">
                Vos identifiants de connexion
            </p>
            <table style="width:100%;font-size:14px;border-collapse:collapse;background:#f8fafc;border-radius:10px;overflow:hidden;">
                <tr>
                    <td style="padding:12px 16px;color:#64748b;font-weight:600;border-bottom:1px solid #e2e8f0;">Email</td>
                    <td style="padding:12px 16px;color:#1a237e;font-weight:700;font-family:monospace;text-align:right;border-bottom:1px solid #e2e8f0;">{to_email}</td>
                </tr>
                <tr>
                    <td style="padding:12px 16px;color:#64748b;font-weight:600;">Mot de passe</td>
                    <td style="padding:12px 16px;color:#1a237e;font-weight:700;font-family:monospace;font-size:16px;text-align:right;">{password}</td>
                </tr>
            </table>
            <div style="text-align:center;margin-top:28px;">
                <a href="{frontend_url}/login"
                   style="display:inline-block;background:#1a237e;color:white;padding:13px 36px;border-radius:10px;text-decoration:none;font-size:14px;font-weight:700;letter-spacing:.03em;">
                    Accéder à mon espace correcteur
                </a>
            </div>
            <div style="background:#fff8f1;border-left:4px solid #f97316;padding:14px;border-radius:0 8px 8px 0;margin-top:24px;">
                <p style="color:#9a3412;font-size:13px;margin:0;line-height:1.5;">
                    Ces identifiants sont strictement personnels. Ne les partagez avec personne.
                </p>
            </div>
        </div>
        <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:20px;">
            © IRISQ — Institut des Risques &amp; de la Qualité
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)


def notify_evaluateur_correction_signed(evaluateur_email: str, correcteur_name: str, correcteur_email: str, candidate_count: int):
    """Notifie l'évaluateur qu'un correcteur a terminé et signé toutes ses corrections."""
    subject = f"Corrections terminées — {correcteur_name}"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    html_body = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:0 auto;background:#f4f6f9;padding:32px 16px;">
        <div style="text-align:center;margin-bottom:28px;">
            <div style="color:#1a237e;font-weight:800;font-size:12px;letter-spacing:0.25em;text-transform:uppercase;">
                IRISQ-CERTIFICATIONS
            </div>
        </div>
        <div style="background:white;border-radius:16px;padding:32px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,.06);">
            <div style="text-align:center;margin-bottom:20px;">
                <div style="display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;background:#e8f5e9;border-radius:50%;">
                    <span style="font-size:28px;">✅</span>
                </div>
            </div>
            <h2 style="color:#1a237e;font-size:20px;font-weight:800;text-align:center;margin:0 0 8px;">
                Corrections signées
            </h2>
            <p style="color:#475569;font-size:14px;line-height:1.7;text-align:center;margin:0 0 24px;">
                Le correcteur <strong>{correcteur_name}</strong> ({correcteur_email})<br>
                a terminé et signé <strong>{candidate_count} correction(s)</strong>.<br>
                Vous pouvez maintenant procéder à l'évaluation finale.
            </p>
            <div style="text-align:center;margin-top:24px;">
                <a href="{frontend_url}/evaluateur/corrections"
                   style="display:inline-block;background:#2e7d32;color:white;padding:13px 36px;border-radius:10px;text-decoration:none;font-size:14px;font-weight:700;">
                    Voir les résultats
                </a>
            </div>
        </div>
        <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:20px;">
            © IRISQ — Institut des Risques &amp; de la Qualité
        </p>
    </div>
    """
    send_email(evaluateur_email, subject, html_body)


def notify_correcteur_relance(to_email: str, full_name: str, pending_count: int, evaluateur_name: str):
    """Envoie une relance au correcteur pour lui rappeler les copies en attente."""
    subject = f"Rappel — {pending_count} copie(s) en attente de correction"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    html_body = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:560px;margin:0 auto;background:#f4f6f9;padding:32px 16px;">
        <div style="text-align:center;margin-bottom:28px;">
            <div style="color:#1a237e;font-weight:800;font-size:12px;letter-spacing:0.25em;text-transform:uppercase;">
                IRISQ-CERTIFICATIONS
            </div>
        </div>
        <div style="background:white;border-radius:16px;padding:32px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,.06);">
            <div style="text-align:center;margin-bottom:20px;">
                <div style="display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;background:#fff3e0;border-radius:50%;">
                    <span style="font-size:28px;">⏰</span>
                </div>
            </div>
            <h2 style="color:#1a237e;font-size:20px;font-weight:800;text-align:center;margin:0 0 8px;">
                Rappel de correction
            </h2>
            <p style="color:#475569;font-size:14px;line-height:1.7;text-align:center;margin:0 0 24px;">
                Bonjour <strong>{full_name}</strong>,<br>
                <strong>{pending_count} copie(s)</strong> vous ont été assignées et sont toujours en attente de correction.<br>
                L'évaluateur <strong>{evaluateur_name}</strong> attend vos corrections.
            </p>
            <div style="background:#fff8f1;border-left:4px solid #f97316;padding:16px;border-radius:0 8px 8px 0;margin-bottom:24px;">
                <p style="color:#9a3412;font-size:14px;margin:0;line-height:1.5;">
                    Merci de vous connecter et de finaliser vos corrections dès que possible.
                </p>
            </div>
            <div style="text-align:center;">
                <a href="{frontend_url}/login"
                   style="display:inline-block;background:#1a237e;color:white;padding:13px 36px;border-radius:10px;text-decoration:none;font-size:14px;font-weight:700;">
                    Accéder à mon espace correcteur
                </a>
            </div>
        </div>
        <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:20px;">
            © IRISQ — Institut des Risques &amp; de la Qualité
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)


def notify_candidate_password_reset(to_email: str, candidate_name: str, public_id: str, new_password: str):
    """Send a freshly generated temporary password after a forgot-password request.

    The candidate will be forced to change it on next login
    (``must_change_password`` is re-enabled by the backend)."""
    subject = f"Réinitialisation de votre mot de passe — {public_id}"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc; padding: 32px;">
        <div style="background: white; border-radius: 16px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="display: inline-block; background: #1a237e; color: white; font-weight: bold; padding: 8px 16px; border-radius: 8px; font-size: 14px; letter-spacing: 0.5px;">
                    IRISQ CERTIFICATION
                </div>
            </div>

            <h2 style="color: #0f172a; font-size: 20px; margin-bottom: 8px; text-align: center;">
                Mot de passe réinitialisé
            </h2>
            <p style="color: #64748b; text-align: center; font-size: 14px; margin-bottom: 24px;">
                Bonjour {candidate_name}, voici votre nouveau mot de passe provisoire pour accéder à votre espace candidat.
            </p>

            <div style="background: #eef2ff; border-left: 4px solid #1a237e; padding: 16px; margin-bottom: 24px; border-radius: 0 8px 8px 0;">
                <table style="width: 100%; font-size: 13px; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden;">
                    <tr>
                        <td style="padding: 10px 12px; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Identifiant</td>
                        <td style="padding: 10px 12px; color: #0f172a; font-weight: 700; font-family: monospace; text-align: right; border-bottom: 1px solid #e2e8f0;">{public_id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 12px; color: #64748b; font-weight: 600;">Mot de passe provisoire</td>
                        <td style="padding: 10px 12px; color: #0f172a; font-weight: 700; font-family: monospace; text-align: right;">{new_password}</td>
                    </tr>
                </table>
                <p style="color: #64748b; font-size: 12px; margin: 10px 0 0 0; line-height: 1.5;">
                    Lors de votre prochaine connexion, vous serez invité(e) à définir un nouveau mot de passe personnel.
                </p>
            </div>

            <div style="text-align: center; margin-bottom: 16px;">
                <a href="{frontend_url}/candidat/login" style="display: inline-block; background: #1a237e; color: white; padding: 12px 28px; border-radius: 10px; text-decoration: none; font-size: 14px; font-weight: 600;">
                    Se connecter à l'espace candidat
                </a>
            </div>

            <div style="background: #fff8f1; border-left: 4px solid #f97316; padding: 14px; margin-top: 16px; border-radius: 0 8px 8px 0;">
                <p style="color: #9a3412; font-size: 13px; margin: 0; line-height: 1.5;">
                    Si vous n'êtes pas à l'origine de cette demande, changez immédiatement votre mot de passe et contactez l'administration.
                </p>
            </div>
        </div>

        <p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 24px;">
            Cet email a été envoyé automatiquement par IRISQ Certification.
        </p>
    </div>
    """
    send_email(to_email, subject, html_body)
