import os
import tempfile
from fpdf import FPDF
from datetime import datetime
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
    
    # Map questions for easy lookup by ID
    q_map = {q.get("id"): q for q in questions} if questions else {}
    
    if not answers:
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(pdf.epw, 10, "Aucune réponse soumise.", new_x="LMARGIN", new_y="NEXT")
    else:
        for i, ans in enumerate(answers, 1):
            q_id = ans.get("question_id")
            answer_text = sanitize_text(ans.get("answer", ""))
            
            question_data = q_map.get(q_id, {})
            question_text = sanitize_text(question_data.get("text", f"Question {i}"))
            question_type = question_data.get("type", "open")
            
            # Print Question Title
            pdf.set_font("helvetica", "B", 11)
            pdf.set_text_color(26, 35, 126) # #1a237e (Dark Independant Blue)
            pdf.cell(pdf.epw, 8, f"Question {i}", new_x="LMARGIN", new_y="NEXT")
            
            # Print Question Text
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(0, 0, 0) # Black
            pdf.multi_cell(pdf.epw, 6, question_text)
            pdf.ln(2)
            
            # Print Options if QCM (just to show context)
            options = question_data.get("options", [])
            if options:
                pdf.set_font("helvetica", "I", 9)
                pdf.set_text_color(100, 100, 100) # Gray
                for opt in options:
                    pdf.multi_cell(pdf.epw, 5, f" - {sanitize_text(opt)}")
                pdf.ln(2)
            
            # Print candidate Answer Header
            pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(46, 125, 50) # #2e7d32 (Green)
            pdf.cell(pdf.epw, 8, "Reponse du candidat :", new_x="LMARGIN", new_y="NEXT")
            
            # Print Candidate Answer Text
            pdf.set_font("helvetica", "", 10)
            if not answer_text.strip():
                pdf.set_text_color(204, 0, 0) # Red
                pdf.multi_cell(pdf.epw, 6, "Aucune réponse fournie.")
            else:
                pdf.set_text_color(0, 0, 0)
                pdf.set_fill_color(248, 249, 250) # Very light gray/bg
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
