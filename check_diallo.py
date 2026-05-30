import asyncio, os, certifi, sys
sys.path.insert(0, os.path.dirname(__file__))
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv()

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=certifi.where())
    db = client[os.getenv("DATABASE_NAME", "irisq_db")]

    docs = await db["responses"].find(
        {"name": {"$regex": "almahdy", "$options": "i"}}
    ).to_list(10)

    for d in docs:
        answers = d.get("answers") or {}
        cert = answers.get("Certification souhaitée") or answers.get("Certification souhaitee", "N/A")
        print("Nom           :", d.get("name"))
        print("Email         :", d.get("email"))
        print("Public ID     :", d.get("public_id"))
        print("Statut        :", d.get("status"))
        print("Soumis le     :", d.get("submitted_at"))
        print("Certification :", cert)
        print("must_change   :", d.get("must_change_password"))
        print()

    client.close()

asyncio.run(main())
