import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt

async def check():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["form_builder"]
    user = await db["users"].find_one({"email": "admin@irisq.sn"})
    if user:
        print("Stored hash:", user["hashed_password"])
        print("Type:", type(user["hashed_password"]))
        res = bcrypt.checkpw(b"password123", user["hashed_password"].encode('utf-8'))
        print("bcrypt.checkpw result:", res)
    else:
        print("User not found")

if __name__ == "__main__":
    asyncio.run(check())
