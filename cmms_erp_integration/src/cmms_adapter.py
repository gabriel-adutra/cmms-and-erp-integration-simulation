"""Adapter responsible for MongoDB operations for CMMS."""
from typing import List, Dict
from datetime import datetime, timezone
from pymongo.errors import (PyMongoError)
from config import Config
from loguru import logger
from mongoDB import MongoService


class CMMSAdapter:

    def __init__(self):
        logger.info("CMMSAdapter initialized...")
        self._mongo = MongoService()
        self._config = Config()
        logger.info("CMMSAdapter ready for operations with CMMS MongoDB.")

    async def get_workorders_collection(self):
        return await self._mongo.get_collection(self._config.MONGO_COLLECTION)
            
    
    async def read_unsynced_workorders(self) -> List[Dict]:
        async def _read_unsynced_workorders():
            workorders = []
            collection = await self.get_workorders_collection()
            
            # Fetch unsynced workorders with deterministic order by number (ascending)
            cursor = collection.find({"isSynced": {"$ne": True}}).sort([("number", 1)])
            
            async for doc in cursor:
                # Convert ObjectId to string for JSON serialization
                doc["_id"] = str(doc["_id"])
                workorders.append(doc)
            
            logger.info(f"Found {len(workorders)} unsynced workorder(s) in CMMS.")
            return workorders
        
        try:
            return await self._mongo.retry_mongo_operation(_read_unsynced_workorders)
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
 
            logger.debug(f"Workorder with number={workorder_data['number']} marked as not synced in CMMS. (isSynced=False)")
            
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
            return await self._mongo.retry_mongo_operation(_upsert_workorder)
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
                logger.debug(f"Workorder with number={number} synced in CMMS. (isSynced=True).")
                return True
            else:
                logger.warning(f"Workorder with number={number} not found in CMMS.")
                return False
        
        try:
            return await self._mongo.retry_mongo_operation(_mark_workorder_as_synced)
        except PyMongoError as e:
            logger.error(f"Error marking workorder {number} as synced: {e}")
            return False
