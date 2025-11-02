"""Shared MongoDB connection utilities (client singleton, health check, helpers)."""

from typing import Optional
import asyncio
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection,
)
from pymongo.errors import (
    PyMongoError,
    NetworkTimeout,
    AutoReconnect,
    ServerSelectionTimeoutError,
    ConnectionFailure,
    NotPrimaryError,
    ExecutionTimeout,
    WTimeoutError,
)
from config import config
from loguru import logger

# Intrinsic timeouts (ms) defined as code constants
SERVER_SELECTION_TIMEOUT_MS = 3000
CONNECT_TIMEOUT_MS = 3000
SOCKET_TIMEOUT_MS = 3000

# Errors considered retriable/transient for connectivity checks.
RETRIABLE_ERRORS = (
    NetworkTimeout,
    AutoReconnect,
    ServerSelectionTimeoutError,
    ConnectionFailure,
    NotPrimaryError,
    ExecutionTimeout,
    WTimeoutError,
)


class MongoService:

    _client: Optional[AsyncIOMotorClient] = None  # per-process singleton

    def __init__(self, uri: Optional[str] = None, database: Optional[str] = None):
        self._uri = uri or config.MONGO_URI
        self._database = database or config.MONGO_DATABASE


    async def _get_mongo_client(self) -> AsyncIOMotorClient:
        """Return the singleton client configured with timeouts."""
        if MongoService._client is None:
            MongoService._client = AsyncIOMotorClient(
                self._uri,
                serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
                connectTimeoutMS=CONNECT_TIMEOUT_MS,
                socketTimeoutMS=SOCKET_TIMEOUT_MS,
            )
        return MongoService._client
    

    async def close(self) -> None:
        """Close the shared client if open."""
        if MongoService._client is not None:
            MongoService._client.close()
            MongoService._client = None


    async def _get_database(self) -> AsyncIOMotorDatabase:
        client = await self._get_mongo_client()
        return client[self._database]
    

    async def get_collection(self, name: str) -> AsyncIOMotorCollection:
        db = await self._get_database()
        return db[name]
    

    async def health_check(self) -> bool:
        """Ping MongoDB; return True if OK, False if unavailable (with logs)."""
        try:
            client = await self._get_mongo_client()
            await client.admin.command("ping")
            logger.info("MongoDB connectivity check: OK.")
            return True
        except RETRIABLE_ERRORS as e:
            logger.error(
                f"MongoDB is not reachable. Is the Docker container running? "
                f"Try: 'docker compose up -d'. Details: {e}"
            )
            return False
        except PyMongoError as e:
            logger.error(f"MongoDB connectivity check failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during MongoDB health check: {e}")
            return False
        

    async def retry_mongo_operation(self, operation_func, *args, **kwargs):
        """Simple retry: up to 3 attempts, 1 second wait between them."""
        max_attempts = 3
        wait_time = 1

        for attempt in range(max_attempts):
            try:
                return await operation_func(*args, **kwargs)
            except RETRIABLE_ERRORS as e:
                if attempt < max_attempts - 1:
                    logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {wait_time}s."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"MongoDB failed after {max_attempts} attempts. Details: {e}"
                    )
                    raise e
            except PyMongoError as e:
                logger.error(f"Permanent MongoDB error: {e}")
                raise e
