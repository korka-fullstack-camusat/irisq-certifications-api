import os
import re
import uuid
import pdfplumber
from docx import Document


# ─────────────────────────────────────────────────────────────────────────────
# Conversion DOCX → HTML (fidèle au document original)
# ─────────────────────────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _runs_to_html(paragraph) -> str:
    """Convertit les runs d'un paragraphe en HTML inline (gras, italique, souligné)."""
    html = ""
    for run in paragraph.runs:
        t = _escape(run.text)
        if not t:
            continue
        if run.bold:
            t = f"<strong>{t}</strong>"
        if run.italic:
            t = f"<em>{t}</em>"
        if run.underline:
            t = f"<u>{t}</u>"
        html += t
    return html


def _paragraph_to_html(para) -> str:
    """Convertit un paragraphe DOCX en balise HTML selon son style."""
    style_name = (para.style.name or "") if para.style else ""
    inner = _runs_to_html(para)

    # Ligne vide → espace
    if not inner.strip():
        return "<p>&nbsp;</p>"

    # Titres
    if "Heading 1" in style_name or "Titre 1" in style_name:
        return f"<h2 style='font-size:1.2em;font-weight:800;margin:1em 0 0.4em;color:#1a237e'>{inner}</h2>"
    if "Heading 2" in style_name or "Titre 2" in style_name:
        return f"<h3 style='font-size:1.05em;font-weight:700;margin:0.9em 0 0.3em;color:#1a237e'>{inner}</h3>"
    if "Heading 3" in style_name or "Titre 3" in style_name:
        return f"<h4 style='font-size:1em;font-weight:700;margin:0.8em 0 0.25em'>{inner}</h4>"

    # Listes
    if "List" in style_name or "Puce" in style_name:
        return f"<li style='margin:0.2em 0'>{inner}</li>"

    # Paragraphe normal
    return f"<p style='margin:0.4em 0;line-height:1.6'>{inner}</p>"


def _table_to_html(table) -> str:
    """Convertit un tableau DOCX en tableau HTML."""
    rows_html = []
    for row_idx, row in enumerate(table.rows):
        cells_html = []
        for cell in row.cells:
            # Contenu de la cellule = plusieurs paragraphes possibles
            cell_content = "".join(_paragraph_to_html(p) for p in cell.paragraphs)
            tag = "th" if row_idx == 0 else "td"
            style = (
                "padding:6px 10px;border:1px solid #ccc;font-weight:700;background:#f4f6f9"
                if row_idx == 0
                else "padding:6px 10px;border:1px solid #e0e0e0"
            )
            cells_html.append(f"<{tag} style='{style}'>{cell_content}</{tag}>")
        rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    return (
        "<table style='border-collapse:collapse;width:100%;margin:0.8em 0'>"
        + "".join(rows_html)
        + "</table>"
    )


def docx_to_html(file_path: str) -> str:
    """
    Convertit un fichier DOCX en HTML en préservant :
    - Titres (Heading 1-3)
    - Gras, italique, souligné
    - Listes (List Bullet / List Number)
    - Tableaux
    - Ordre original paragraphes + tableaux
    """
    try:
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph as DocxParagraph

        doc = Document(file_path)
        parts = [
            "<div style='font-family:inherit;font-size:0.9em;line-height:1.7;"
            "color:#1a1a2e;padding:4px 0'>"
        ]

        for child in doc.element.body.iterchildren():
            local_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if local_tag == "p":
                para = DocxParagraph(child, doc)
                parts.append(_paragraph_to_html(para))

            elif local_tag == "tbl":
                table = Table(child, doc)
                parts.append(_table_to_html(table))

        parts.append("</div>")
        return "".join(parts)

    except Exception as e:
        print(f"[docx_to_html] Erreur : {e}")
        return ""


def pdf_to_html(file_path: str) -> str:
    """Extrait le texte d'un PDF et le retourne sous forme de HTML basique."""
    try:
        parts = ["<div style='font-family:inherit;font-size:0.9em;line-height:1.7;color:#1a1a2e'>"]
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    escaped = _escape(line)
                    if escaped.strip():
                        parts.append(f"<p style='margin:0.3em 0'>{escaped}</p>")
                    else:
                        parts.append("<p>&nbsp;</p>")
        parts.append("</div>")
        return "".join(parts)
    except Exception as e:
        print(f"[pdf_to_html] Erreur : {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Parseur de questions (mode interactif — format numéroté)
# ─────────────────────────────────────────────────────────────────────────────

def parse_exam_document(file_path: str) -> list:
    """
    Lit un PDF ou DOCX et extrait les questions/options selon un formatage attendu.
    Retourne une liste de questions pour le mode interactif.
    """
    if not os.path.exists(file_path):
        return []

    ext = os.path.splitext(file_path)[1].lower()
    raw_text = ""

    try:
        if ext == ".pdf":
            with pdfplumber.open(file_path) as pdf:
                raw_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        elif ext in [".doc", ".docx"]:
            doc = Document(file_path)
            raw_text = "\n".join(p.text for p in doc.paragraphs)
        else:
            return []
    except Exception as e:
        print(f"Error reading document: {e}")
        return []

    return parse_exam_text(raw_text)


def parse_exam_text(raw_text: str) -> list:
    questions = []
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    current_part = "Examen"
    current_q = None

    for line in lines:
        if line.upper().startswith("PARTIE "):
            current_part = line
            continue

        # Match "1. La norme ISO..." ou "Cas 1 : Un laboratoire..."
        q_match = re.match(r"^((?:\d+\.)|(?:Cas\s+\d+\s*:))\s*(.*)", line, re.IGNORECASE)
        # Match "A. Les laboratoires médicaux"
        opt_match = re.match(r"^([A-D]\.)\s*(.*)", line)

        if q_match and "QCM" not in line:
            if current_q:
                questions.append(current_q)
            q_type = "qcm" if "QCM" in current_part.upper() else "open"
            current_q = {
                "id": str(uuid.uuid4()),
                "part": current_part,
                "type": q_type,
                "text": line,
                "options": [],
            }
        elif opt_match and current_q and current_q["type"] == "qcm":
            current_q["options"].append(line)
        elif current_q and not q_match and not opt_match and not line.upper().startswith("PARTIE "):
            current_q["text"] += "\n" + line

    if current_q:
        questions.append(current_q)

    return questions
