"""
suivi.py — Tableau de bord candidats en temps reel.
Execution : python suivi.py
"""

import asyncio
import os
import certifi
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=certifi.where())
    db = client[os.getenv("DATABASE_NAME", "irisq_db")]

    candidats = await db["responses"].find({}).sort("submitted_at", 1).to_list(1000)

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    print()
    print("=" * 108)
    print(f"  SUIVI CANDIDATS  —  {now}  —  {len(candidats)} dossier(s)")
    print("=" * 108)
    print(f"  {'#':<4} {'NOM':<26} {'FORMATION':<34} {'DOSSIER':<12} {'EXAMEN':<14} {'CORRECTION':<14} {'RESULTAT'}")
    print("-" * 108)

    stats = {"pending": 0, "approved": 0, "rejected": 0}
    examen_stats = {"Non convoque": 0, "Convoque": 0, "Passe": 0}

    for i, c in enumerate(candidats, 1):
        answers       = c.get("answers") or {}
        certification = (
            answers.get("Certification souhaitée")
            or answers.get("Certification souhaitee")
            or "N/A"
        )
        name      = c.get("name", "N/A")
        public_id = c.get("public_id", "N/A")
        status    = c.get("status", "pending")

        # --- Dossier ---
        dossier_label = {
            "pending" : "En attente",
            "approved": "Valide",
            "rejected": "Refuse",
        }.get(status, status)
        stats[status] = stats.get(status, 0) + 1

        # --- Examen ---
        if c.get("exam_answers") or c.get("exam_document"):
            examen_label = "Passe"
            examen_stats["Passe"] += 1
        elif c.get("exam_token"):
            examen_label = "Convoque"
            examen_stats["Convoque"] += 1
        else:
            examen_label = "Non convoque"
            examen_stats["Non convoque"] += 1

        # --- Correction ---
        answer_grades = c.get("answer_grades")
        jury_grades   = c.get("jury_answer_grades")
        if jury_grades:
            correction_label = "Jury OK"
        elif answer_grades:
            correction_label = "Correcteur OK"
        else:
            correction_label = "-"

        # --- Resultat final ---
        final_grade = c.get("final_grade")
        final_appr  = c.get("final_appreciation")
        exam_grade  = c.get("exam_grade")
        if final_appr:
            resultat = final_appr[:12]
        elif final_grade is not None:
            resultat = f"Note: {final_grade}"
        elif exam_grade is not None:
            resultat = f"Note: {exam_grade}"
        else:
            resultat = "-"

        print(f"  {i:<4} {name[:25]:<26} {certification[:33]:<34} {dossier_label:<12} {examen_label:<14} {correction_label:<14} {resultat}")

    print("=" * 108)

    # --- Resumé ---
    print()
    print("  RESUME")
    print(f"  Dossiers  : {stats.get('approved',0)} valides  |  {stats.get('pending',0)} en attente  |  {stats.get('rejected',0)} refuses")
    print(f"  Examens   : {examen_stats['Passe']} passes  |  {examen_stats['Convoque']} convoques  |  {examen_stats['Non convoque']} non convoques")
    print("=" * 108)
    print()

    client.close()

asyncio.run(main())
