import re
import json

text = """Examen Blanc – Lead Implementor ISO/IEC 17025:2017
Durée : 2h
Type : QCM – Questions ouvertes – Études de cas

PARTIE 1 : QCM
1. La norme ISO/IEC 17025:2017 concerne :
A. Les laboratoires médicaux
B. Les laboratoires d’essais et d’étalonnage
C. Les organismes de certification
D. Les hôpitaux

2. L’impartialité signifie :
A. L’absence de procédure
B. L’absence de conflit d’intérêt
C. La compétence du personnel
D. La confidentialité

3. Le management des risques est traité principalement dans :
A. Clause 4
B. Clause 5
C. Clause 6
D. Clause 8

PARTIE 2 : Questions ouvertes
1. Expliquez le principe d’impartialité et son importance dans un laboratoire.
2. Décrivez les exigences relatives à la compétence du personnel.
3. Quelle est la différence entre validation et vérification des méthodes ?
PARTIE 3 : Études de cas
Cas 1 : Un laboratoire reçoit des plaintes répétées sur la fiabilité de ses résultats. Expliquez les actions à mettre en œuvre selon ISO/IEC 17025.
Cas 2 : Un technicien n’a pas reçu de formation mais réalise des essais critiques. Quels risques et quelles mesures correctives proposer ?"""

def parse_exam_text(raw_text):
    questions = []
    lines = [L.strip() for L in raw_text.split('\n') if L.strip()]
    
    current_part = ""
    current_q = None
    
    for i, line in enumerate(lines):
        if line.upper().startswith("PARTIE "):
            current_part = line
            continue
            
        # Match QCM or Open Questions (e.g. "1. Question", "Cas 1 : Question")
        q_match = re.match(r'^((?:\d+\.)|(?:Cas\s+\d+\s*:))\s*(.*)', line, re.IGNORECASE)
        opt_match = re.match(r'^([A-Z]\.)\s*(.*)', line)
        
        if q_match and not "QCM" in line:
            if current_q:
                questions.append(current_q)
            
            q_type = "qcm" if "QCM" in current_part.upper() else "open"
            
            current_q = {
                "id": f"q_{len(questions)}",
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

print(json.dumps(parse_exam_text(text), indent=2, ensure_ascii=False))
