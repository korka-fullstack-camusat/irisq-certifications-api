import requests
import json

url = "http://127.0.0.1:8000/api/forms"
payload = {
    "title": "Fiche de demande - IRISQ CERTIFICATION",
    "description": "Formulaire demande de certification PGC-ENR-06-01\nJe déclare que, à ma connaissance, toutes les informations fournies dans la présente demande ainsi que ses pièces jointes sont vraies, correctes, complètes et à jour. Aussi, j’autorise par la présente IRISQ Certification à procéder à toutes les vérifications qu’il jugera nécessaires.",
    "category": "Certification",
    "status": "active",
    "fields": [
        {"id": "nom", "type": "text", "label": "Nom", "required": True},
        {"id": "dna", "type": "date", "label": "Date de naissance", "required": True},
        {"id": "nat", "type": "text", "label": "Nationalité", "required": False},
        {"id": "tel", "type": "text", "label": "Téléphone", "required": True},
        {"id": "cert", "type": "radio", "label": "Certification souhaitée", "description": "Sélectionnez la certification", "required": True},
        {"id": "amenage", "type": "radio", "label": "Demande d'aménagement spécifique (Oui/Non)", "required": True},
        {"id": "docs", "type": "file_upload", "label": "Documents joints (CV, Cartes, Diplômes...)", "required": True},
        {"id": "decl", "type": "checkbox", "label": "Je certifie sur l'honneur l'exactitude des informations.", "required": True}
    ]
}

try:
    res = requests.post(url, json=payload)
    if res.status_code in [200, 201]:
        data = res.json()
        print("Formulaire créé avec succès !", data)
        print("Test URL: http://localhost:3000/f/" + data.get("id", data.get("_id", "unknown")))
    else:
        print("Erreur HTTP:", res.status_code, res.text)
except Exception as e:
    print("Exception lors de l'appel:", e)
