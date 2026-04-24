import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_form_builder")

MONGO_TIMEOUT_MS = 15000
MONGO_POOL_SIZE = int(os.getenv("MONGO_POOL_SIZE", "200"))


class Database:
    client: AsyncIOMotorClient = None
    db = None
    fs: AsyncIOMotorGridFSBucket = None


db_instance = Database()


def _build_client() -> AsyncIOMotorClient:
    # TLS knobs tuned for MongoDB Atlas:
    # - tlsCAFile=certifi.where(): avoid Windows system trust store issues
    # - tlsDisableOCSPEndpointCheck=True: OCSP fetch frequently times out or
    #   fails on Windows with Python 3.14, which Atlas reports back as
    #   "TLSV1_ALERT_INTERNAL_ERROR"
    # - retryWrites/appName are forwarded via MONGO_URI
    return AsyncIOMotorClient(
        MONGO_URI,
        maxPoolSize=MONGO_POOL_SIZE,
        minPoolSize=10,
        maxIdleTimeMS=45000,
        waitQueueTimeoutMS=5000,
        serverSelectionTimeoutMS=MONGO_TIMEOUT_MS,
        connectTimeoutMS=10000,
        socketTimeoutMS=45000,
        retryWrites=True,
        tls=True,
        tlsCAFile=certifi.where(),
        tlsDisableOCSPEndpointCheck=True,
    )


async def connect_to_mongo():
    db_instance.client = _build_client()
    db_instance.db = db_instance.client[DATABASE_NAME]
    db_instance.fs = AsyncIOMotorGridFSBucket(db_instance.db)


async def close_mongo_connection():
    if db_instance.client:
        db_instance.client.close()


def get_database():
    if db_instance.db is None:
        db_instance.client = _build_client()
        db_instance.db = db_instance.client[DATABASE_NAME]
        db_instance.fs = AsyncIOMotorGridFSBucket(db_instance.db)
    return db_instance.db


def get_fs():
    if db_instance.fs is None:
        db_instance.client = _build_client()
        db_instance.db = db_instance.client[DATABASE_NAME]
        db_instance.fs = AsyncIOMotorGridFSBucket(db_instance.db)
    return db_instance.fs
