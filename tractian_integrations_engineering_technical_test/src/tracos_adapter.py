"""Adapter responsible for MongoDB operations for TracOS."""

import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import (PyMongoError, NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ConnectionFailure, NotPrimaryError, ExecutionTimeout, WTimeoutError)
from config import config
from loguru import logger


class TracosAdapter:
    
    def __init__(self):
        logger.info("TracosAdapter initialized...")
        self._mongo_client: Optional[AsyncIOMotorClient] = None
        logger.info("TracosAdapter ready for operations with TracOS MongoDB.")

    
    async def get_mongo_client(self) -> AsyncIOMotorClient:
        if self._mongo_client is None:
            self._mongo_client = AsyncIOMotorClient(config.MONGO_URI)
        return self._mongo_client
    
    
    async def close_connection(self):
        if self._mongo_client is not None:
            self._mongo_client.close()
            self._mongo_client = None
    
    
    async def get_workorders_collection(self) -> AsyncIOMotorCollection:
        mongo_client = await self.get_mongo_client()
        db = mongo_client[config.MONGO_DATABASE]
        return db[config.MONGO_COLLECTION]
    
    
    # Exceptions that should be retried (temporary network/connection issues)
    RETRIABLE_ERRORS = (
        NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError,
        ConnectionFailure, NotPrimaryError, ExecutionTimeout, WTimeoutError
    )
    async def _retry_mongo_operation(self, operation_func, *args, **kwargs):
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                return await operation_func(*args, **kwargs)
                
            except self.RETRIABLE_ERRORS as e:
                if attempt < max_attempts - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s.")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"MongoDB failed after {max_attempts} attempts. Details: {e}")
                    raise e
                    
            except PyMongoError as e:
                logger.error(f"MongoDB permanent error: {e}")
                raise e
            
    
    async def read_unsynced_workorders(self) -> List[Dict]:
        async def _read_unsynced_workorders():
            workorders = []
            collection = await self.get_workorders_collection()
            
            # Fetch unsynced workorders
            cursor = collection.find({"isSynced": {"$ne": True}})
            
            async for doc in cursor:
                # Convert ObjectId to string for JSON serialization
                doc["_id"] = str(doc["_id"])
                workorders.append(doc)
            
            logger.info(f"Found {len(workorders)} unsynced workorder(s) in TracOS.")
            return workorders
        
        try:
            return await self._retry_mongo_operation(_read_unsynced_workorders)
        except PyMongoError as e:
            logger.error(f"Error reading unsynced workorders. Details: {e}")
            return []
        
    
    async def upsert_workorder(self, workorder_data: Dict) -> bool:
        async def _upsert_workorder():
            collection = await self.get_workorders_collection()
            
            # Use 'number' as unique key to identify workorders
            filter_query = {"number": workorder_data["number"]}
            
            # Add sync control fields
            workorder_data_copy = workorder_data.copy()
            workorder_data_copy.update({
                "isSynced": False,
                "updatedAt": datetime.now(timezone.utc)
            })
 
            logger.debug(f"Workorder with number={workorder_data['number']} marked as not synced in TracOS. (isSynced=False)")
            
            # Upsert: update if exists, insert if not, removing syncedAt
            result = await collection.update_one(
                filter_query,
                {
                    "$set": workorder_data_copy,
                    "$unset": {"syncedAt": ""}
                },
                upsert=True
            )

            action = "inserted" if result.upserted_id else "updated"
            logger.debug(f"Workorder with number={workorder_data['number']} was {action}.")
            return True
        
        try:
            return await self._retry_mongo_operation(_upsert_workorder)
        except PyMongoError as e:
            logger.error(f"Error saving workorder {workorder_data.get('number')}: {e}")
            return False
        
    
    async def mark_workorder_as_synced(self, number: int) -> bool:
        async def _mark_workorder_as_synced():
            collection = await self.get_workorders_collection()
            result = await collection.update_one(
                {"number": number},
                {
                    "$set": {
                        "isSynced": True,
                        "syncedAt": datetime.now(timezone.utc)
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.debug(f"Workorder with number={number} synced in TracOS. (isSynced=True).")
                return True
            else:
                logger.warning(f"Workorder with number={number} not found in TracOS.")
                return False
        
        try:
            return await self._retry_mongo_operation(_mark_workorder_as_synced)
        except PyMongoError as e:
            logger.error(f"Error marking workorder {number} as synced: {e}")
            return False
        
            




tracos_adapter = TracosAdapter()

