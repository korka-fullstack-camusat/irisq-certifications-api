import logging
import os

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

load_dotenv()

logger = logging.getLogger(__name__)

MONGO_URI      = os.getenv("MONGO_URI")
DATABASE_NAME  = os.getenv("DATABASE_NAME", "irisq_form_builder")
MONGO_POOL_SIZE = int(os.getenv("MONGO_POOL_SIZE", "200"))
MONGO_TIMEOUT_MS = 15000


class Database:
    client: AsyncIOMotorClient = None
    db = None
    fs: AsyncIOMotorGridFSBucket = None


db_instance = Database()


def _build_client() -> AsyncIOMotorClient:
    """Crée un nouveau client Motor avec les paramètres Atlas optimisés."""
    return AsyncIOMotorClient(
        MONGO_URI,
        maxPoolSize=MONGO_POOL_SIZE,
        minPoolSize=5,
        maxIdleTimeMS=30000,          # ferme les connexions inactives après 30 s
        waitQueueTimeoutMS=8000,       # attend 8 s avant d'abandonner
        serverSelectionTimeoutMS=MONGO_TIMEOUT_MS,
        connectTimeoutMS=10000,
        socketTimeoutMS=45000,
        retryWrites=True,
        tls=True,
        tlsCAFile=certifi.where(),
        tlsDisableOCSPEndpointCheck=True,
    )


def _init_instance(client: AsyncIOMotorClient) -> None:
    db_instance.client = client
    db_instance.db     = client[DATABASE_NAME]
    db_instance.fs     = AsyncIOMotorGridFSBucket(db_instance.db)


async def connect_to_mongo():
    _init_instance(_build_client())
    logger.info("MongoDB connecté (base : %s)", DATABASE_NAME)


async def close_mongo_connection():
    if db_instance.client:
        db_instance.client.close()
        db_instance.client = None
        db_instance.db     = None
        db_instance.fs     = None
        logger.info("MongoDB déconnecté.")


# ── Accesseurs synchrones (compatibilité existante) ──────────────────────────

def get_database():
    if db_instance.db is None:
        _init_instance(_build_client())
    return db_instance.db


def get_fs():
    if db_instance.fs is None:
        _init_instance(_build_client())
    return db_instance.fs


# ── Accesseur async robuste (utilisé par upload.py) ─────────────────────────

async def ensure_fs(force_reconnect: bool = False) -> AsyncIOMotorGridFSBucket:
    """
    Retourne le bucket GridFS en s'assurant que la connexion est vivante.
    Si `force_reconnect=True` ou que la connexion est absente, recrée le client.
    """
    if force_reconnect or db_instance.fs is None:
        if db_instance.client:
            try:
                db_instance.client.close()
            except Exception:
                pass
        _init_instance(_build_client())
        logger.info("MongoDB reconnecté (force=%s).", force_reconnect)

    # Ping léger pour détecter une connexion silencieusement fermée
    try:
        await db_instance.db.command("ping")
    except Exception as exc:
        logger.warning("Ping MongoDB échoué (%s) — reconnexion…", exc)
        _init_instance(_build_client())
        await db_instance.db.command("ping")   # lève si toujours KO

    return db_instance.fs
