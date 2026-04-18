import os
import re
import uuid
import pdfplumber
from docx import Document

def parse_exam_document(file_path: str) -> list:
    """
    Reads a PDF or DOCX file and extracts questions and options
    based on expected formatting.
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
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    
    current_part = "Examen"
    current_q = None
    
    for line in lines:
        if line.upper().startswith("PARTIE "):
            current_part = line
            continue
            
        # Match "1. La norme ISO..." or "Cas 1 : Un laboratoire..."
        q_match = re.match(r'^((?:\d+\.)|(?:Cas\s+\d+\s*:))\s*(.*)', line, re.IGNORECASE)
        # Match "A. Les laboratoires médicaux"
        opt_match = re.match(r'^([A-D]\.)\s*(.*)', line)
        
        if q_match and not "QCM" in line:
            if current_q:
                questions.append(current_q)
            
            # Determine if it's QCM based on the section title
            q_type = "qcm" if "QCM" in current_part.upper() else "open"
            
            current_q = {
                "id": str(uuid.uuid4()),
                "part": current_part,
                "type": q_type,
                "text": line,
                "options": []
            }
        elif opt_match and current_q and current_q["type"] == "qcm":
            current_q["options"].append(line)
        elif current_q and not q_match and not opt_match and not line.upper().startswith("PARTIE "):
            current_q["text"] += "\n" + line
            
    if current_q:
        questions.append(current_q)
        
    return questions
