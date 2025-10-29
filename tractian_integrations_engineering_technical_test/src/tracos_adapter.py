""" Adaptador para operações MongoDB do sistema TracOS. """

import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import (
    PyMongoError, NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError,
    ConnectionFailure, NotPrimaryError, ExecutionTimeout, WTimeoutError
)
from config import config
from loguru import logger

# Exceções que merecem retry (problemas temporários)
RETRIABLE_ERRORS = (
    NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError,
    ConnectionFailure, NotPrimaryError, ExecutionTimeout, WTimeoutError
)


async def retry_mongo_operation(operation_func, *args, **kwargs):
    """Retry simples para operações MongoDB com problemas temporários."""
    for attempt in range(3):
        try:
            return await operation_func(*args, **kwargs)
        except RETRIABLE_ERRORS as e:
            if attempt < 2:
                await asyncio.sleep(1)
                continue
            raise e
        except PyMongoError as e:
            # Erro permanente - não retry
            raise e


async def get_mongo_client() -> AsyncIOMotorClient:
    """Conecta ao MongoDB."""
    return AsyncIOMotorClient(config.MONGO_URI)


async def get_collection() -> AsyncIOMotorCollection:
    """Retorna a collection de workorders."""
    client = await get_mongo_client()
    db = client[config.MONGO_DATABASE]
    return db[config.MONGO_COLLECTION]


async def read_unsynced_workorders() -> List[Dict]:
    """Lê workorders com isSynced=false do MongoDB."""
    async def _read():
        workorders = []
        collection = await get_collection()
        cursor = collection.find({"isSynced": {"$ne": True}})
        
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            workorders.append(doc)
            
        logger.info(f"Workorders não sincronizadas encontradas: {len(workorders)}")
        return workorders
    
    try:
        return await retry_mongo_operation(_read)
    except PyMongoError as e:
        logger.error(f"Erro ao ler workorders após tentativas: {e}")
        return []


async def upsert_workorder(workorder_data: Dict) -> bool:
    """Insere ou atualiza workorder no MongoDB."""
    async def _upsert():
        collection = await get_collection()
        
        # Usar number como chave única para upsert
        filter_query = {"number": workorder_data["number"]}
        
        # Adicionar campos de controle
        workorder_data["isSynced"] = False
        workorder_data["updatedAt"] = datetime.now(timezone.utc)
        
        result = await collection.update_one(
            filter_query,
            {"$set": workorder_data},
            upsert=True
        )
        
        action = "inserido" if result.upserted_id else "atualizado"
        logger.info(f"Workorder {workorder_data['number']} {action}")
        
    try:
        await retry_mongo_operation(_upsert)
        return True
    except PyMongoError as e:
        logger.error(f"Erro ao salvar workorder {workorder_data.get('number')} após tentativas: {e}")
        return False


async def mark_as_synced(number: int) -> bool:
    """Marca workorder como sincronizada."""
    async def _mark():
        collection = await get_collection()
        
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
            logger.info(f"Workorder {number} marcada como sincronizada")
            return True
        else:
            logger.warning(f"Workorder {number} não encontrada para marcação")
            return False
            
    try:
        return await retry_mongo_operation(_mark)
    except PyMongoError as e:
        logger.error(f"Erro ao marcar workorder {number} após tentativas: {e}")
        return False