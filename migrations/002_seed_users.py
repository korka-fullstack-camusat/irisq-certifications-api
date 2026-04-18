import bcrypt
from datetime import datetime


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def up(db):
    users = [
        {
            "email": "admin@irisq.sn",
            "password": "password123",
            "role": "RH",
            "full_name": "Administrateur RH",
        },
        {
            "email": "evaluateur@irisq.sn",
            "password": "jury123",
            "role": "EVALUATEUR",
            "full_name": "Membre du Jury",
        },
        {
            "email": "correcteur@irisq.sn",
            "password": "exam123",
            "role": "CORRECTEUR",
            "full_name": "Correcteur Anonyme",
        },
    ]

    for u in users:
        existing = await db["users"].find_one({"email": u["email"]})
        if not existing:
            await db["users"].insert_one(
                {
                    "email": u["email"],
                    "hashed_password": _hash(u["password"]),
                    "role": u["role"],
                    "full_name": u["full_name"],
                    "created_at": datetime.utcnow(),
                }
            )
