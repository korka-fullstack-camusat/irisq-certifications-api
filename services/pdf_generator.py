import os
import re
import tempfile
from fpdf import FPDF
from datetime import datetime
from html import unescape
from database import get_fs

class PDF(FPDF):
    def header(self):
        # Logo could be added here if available locally
        self.set_font("helvetica", "B", 15)
        self.cell(self.epw, 10, "Copie d'Examen Candidat", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(self.epw, 10, f"Page {self.page_no()}/{{nb}}", 0, 0, "C")

def html_to_plain_text(html: str) -> str:
    """Convert RichTextEditor HTML to plain text for PDF output."""
    if not html:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '  - ', text, flags=re.IGNORECASE)
    text = re.sub(r'<h[1-6][^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</h[1-6]>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</td>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'</th>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def sanitize_text(text: str) -> str:
    """Removes or replaces characters not supported by standard FPDF2 helvetica (latin-1)."""
    if not isinstance(text, str):
        return str(text)
    
    replacements = {
        '’': "'", '‘': "'", '“': '"', '”': '"', '«': '"', '»': '"',
        '–': '-', '—': '-', '…': '...', '€': 'EUR', 'œ': 'oe', 'Œ': 'OE',
        '\u2028': '\n', '\u2029': '\n', '•': '-'
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
        
    return text.encode('latin-1', 'ignore').decode('latin-1')

async def generate_and_upload_candidate_pdf(candidate_info: dict, questions: list, answers: list, cheat_alerts: list) -> str:
    """
    Generates a PDF spanning the questions, candidate answers, and anti-cheat logs,
    then uploads it to GridFS and returns the /api/files/id URL.
    """
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Enable automatic page breaking
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # ── 1. Candidate Info ──
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(pdf.epw, 10, "Informations Candidat", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    
    # candidate_info should have ID and Certification
    c_id = sanitize_text(candidate_info.get("candidate_id", "Inconnu"))
    c_cert = sanitize_text(candidate_info.get("certification", "Non specifiee"))
    c_date = datetime.utcnow().strftime("%d/%m/%Y %H:%M")
    
    pdf.cell(pdf.epw, 8, f"ID Candidat : {c_id}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 8, f"Certification : {c_cert}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 8, f"Date de soumission : {c_date}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # ── 2. Exam Answers ──
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(pdf.epw, 10, "Réponses à l'Examen", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    # ── Maps pour la recherche ──────────────────────────────────────────────────
    # q_map : id principal → question
    q_map = {q.get("id"): q for q in questions} if questions else {}

    # parts_map : part_id → (question_parente, part_data)
    parts_map: dict = {}
    for q in (questions or []):
        for part in q.get("parts", []):
            if part.get("id"):
                parts_map[part["id"]] = (q, part)

    # ── Regrouper les réponses par question parente ──────────────────────────
    # Structure : { question_id: { "question": q_data, "direct": answer, "parts": {part_id: answer} } }
    grouped: dict = {}

    for ans in (answers or []):
        q_id   = ans.get("question_id", "")
        value  = ans.get("answer", "")

        if q_id in q_map:
            # Réponse directe à une question standard
            if q_id not in grouped:
                grouped[q_id] = {"question": q_map[q_id], "direct": "", "parts": {}}
            grouped[q_id]["direct"] = value

        else:
            # Essayer de retrouver la question parente pour les réponses composées
            # Format : "main_uuid_part_uuid"  (les deux UUIDs séparés par "_")
            found = False
            # Vérifier si le q_id commence par un main_id connu
            for main_id, q_data in q_map.items():
                if q_id.startswith(main_id + "_"):
                    part_id = q_id[len(main_id) + 1:]
                    if main_id not in grouped:
                        grouped[main_id] = {"question": q_data, "direct": "", "parts": {}}
                    grouped[main_id]["parts"][part_id] = value
                    found = True
                    break

            if not found:
                # Réponse orpheline (question supprimée ou format inconnu)
                if q_id not in grouped:
                    grouped[q_id] = {"question": {}, "direct": value, "parts": {}}
                else:
                    grouped[q_id]["direct"] = value

    if not grouped:
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(pdf.epw, 10, "Aucune reponse soumise.", new_x="LMARGIN", new_y="NEXT")
    else:
        # Trier par ordre d'apparition dans le document (questions)
        q_order = [q.get("id") for q in (questions or [])]
        sorted_ids = sorted(
            grouped.keys(),
            key=lambda k: q_order.index(k) if k in q_order else 9999
        )

        for i, q_id in enumerate(sorted_ids, 1):
            entry    = grouped[q_id]
            q_data   = entry["question"]
            q_text   = sanitize_text(q_data.get("text", f"Question {i}"))
            q_type   = q_data.get("type", "open")
            parts    = q_data.get("parts", [])

            # ── Titre de la question ──────────────────────────────────────
            pdf.set_font("helvetica", "B", 11)
            pdf.set_text_color(26, 35, 126)
            pdf.cell(pdf.epw, 8, f"Question {i}", new_x="LMARGIN", new_y="NEXT")

            # ── Texte de la question ──────────────────────────────────────
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(pdf.epw, 6, q_text)
            pdf.ln(2)

            # ── Options QCM (contexte) ────────────────────────────────────
            options = q_data.get("options", [])
            if options:
                pdf.set_font("helvetica", "I", 9)
                pdf.set_text_color(100, 100, 100)
                for opt in options:
                    pdf.multi_cell(pdf.epw, 5, f" - {sanitize_text(opt)}")
                pdf.ln(2)

            # ── Réponses ──────────────────────────────────────────────────
            if q_type == "compound" and parts:
                # Questions composées Vrai/Faux : afficher chaque sous-partie
                for part in parts:
                    part_id    = part.get("id", "")
                    part_label = sanitize_text(part.get("label", ""))
                    part_type  = part.get("type", "open")
                    part_value = entry["parts"].get(part_id, "")

                    # Label de la sous-question
                    pdf.set_font("helvetica", "B", 9)
                    pdf.set_text_color(70, 70, 70)
                    pdf.cell(pdf.epw, 6, part_label, new_x="LMARGIN", new_y="NEXT")

                    # Réponse
                    pdf.set_font("helvetica", "", 10)
                    if part_type == "vraifaux":
                        # Afficher Vrai/Faux avec couleur
                        if part_value == "Vrai":
                            pdf.set_text_color(46, 125, 50)  # vert
                            pdf.set_fill_color(232, 245, 233)
                            pdf.cell(pdf.epw, 7, "  Vrai", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                        elif part_value == "Faux":
                            pdf.set_text_color(198, 40, 40)  # rouge
                            pdf.set_fill_color(255, 235, 238)
                            pdf.cell(pdf.epw, 7, "  Faux", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                        else:
                            pdf.set_text_color(204, 0, 0)
                            pdf.multi_cell(pdf.epw, 6, "Non repondu.")
                    else:
                        # Réponse texte libre
                        clean = sanitize_text(html_to_plain_text(part_value))
                        if clean.strip():
                            pdf.set_text_color(0, 0, 0)
                            pdf.set_fill_color(248, 249, 250)
                            pdf.multi_cell(pdf.epw, 6, clean, border=1, fill=True)
                        else:
                            pdf.set_text_color(204, 0, 0)
                            pdf.multi_cell(pdf.epw, 6, "Aucune reponse fournie.")
                    pdf.ln(2)

            else:
                # Question standard (QCM ou ouverte)
                pdf.set_font("helvetica", "B", 10)
                pdf.set_text_color(46, 125, 50)
                pdf.cell(pdf.epw, 8, "Reponse du candidat :", new_x="LMARGIN", new_y="NEXT")

                answer_text = sanitize_text(html_to_plain_text(entry["direct"]))
                pdf.set_font("helvetica", "", 10)
                if not answer_text.strip():
                    pdf.set_text_color(204, 0, 0)
                    pdf.multi_cell(pdf.epw, 6, "Aucune reponse fournie.")
                else:
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_fill_color(248, 249, 250)
                    pdf.multi_cell(pdf.epw, 6, answer_text, border=1, fill=True)

            pdf.ln(8)
            

    
    # Save to temp file
    ext = ".pdf"
    unique_filename = f"copie_{c_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{ext}"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        pdf.output(temp_file.name)
        temp_path = temp_file.name
        
    try:
        # Upload to GridFS
        fs = get_fs()
        with open(temp_path, "rb") as f:
            content = f.read()
            
        file_id = await fs.upload_from_stream(
            unique_filename,
            content,
            metadata={"content_type": "application/pdf", "original_name": unique_filename}
        )
        
        return f"/api/files/{str(file_id)}"
    except Exception as e:
        print(f"Error uploading PDF: {e}")
        return ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
