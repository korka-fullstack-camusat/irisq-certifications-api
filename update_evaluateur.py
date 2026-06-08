"""
update_evaluateur.py
--------------------
Met a jour le mot de passe du compte agnideobed.assogba@irisq.sn
"""
import asyncio, os, certifi
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

MONGO_URI     = os.getenv("MONGO_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_db")
pwd_ctx       = CryptContext(schemes=["bcrypt"], deprecated="auto")

TARGET_EMAIL = "agnideobed.assogba@irisq.sn"
NEW_PASSWORD = "jury@123"

async def main():
    client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db     = client[DATABASE_NAME]

    user = await db["users"].find_one({"email": TARGET_EMAIL})
    if not user:
        print(f"[ERREUR] Aucun compte trouve avec l'email : {TARGET_EMAIL}")
        client.close()
        return

    print(f"\nCompte trouve : {user.get('email')} [{user.get('role')}]")

    new_hash = pwd_ctx.hash(NEW_PASSWORD)
    await db["users"].update_one(
        {"email": TARGET_EMAIL},
        {"$set": {"hashed_password": new_hash, "role": "EVALUATEUR"}}
    )

    print(f"[OK] Mis a jour pour : {TARGET_EMAIL}")
    print(f"     Nouveau mot de passe : {NEW_PASSWORD}")
    print(f"     Nouveau role         : EVALUATEUR")
    client.close()

asyncio.run(main())
