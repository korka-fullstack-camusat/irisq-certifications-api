import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def get_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

async def seed_users():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    db = client[os.getenv("DATABASE_NAME", "irisq_form_builder")]

    users_to_seed = [
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
        }
    ]

    for u in users_to_seed:
        existing = await db["users"].find_one({"email": u["email"]})
        if not existing:
            hashed_password = get_hash(u["password"])
            new_user = {
                "email": u["email"],
                "hashed_password": hashed_password,
                "role": u["role"],
                "full_name": u["full_name"],
                "created_at": datetime.utcnow()
            }
            await db["users"].insert_one(new_user)
            print(f"User {u['email']} created.")
        else:
            print(f"User {u['email']} already exists.")
            # Update password just in case
            await db["users"].update_one(
                {"email": u["email"]},
                {"$set": {"hashed_password": get_hash(u["password"])}}
            )
            print(f"User {u['email']} password updated.")

    print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_users())
