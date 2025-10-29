""" Adaptador para operações MongoDB do sistema TracOS. """

from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import PyMongoError
from config import config
from loguru import logger


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
    workorders = []
    
    try:
        collection = await get_collection()
        cursor = collection.find({"isSynced": {"$ne": True}})
        
        async for doc in cursor:
            # Converter ObjectId para string para serialização JSON
            doc["_id"] = str(doc["_id"])
            workorders.append(doc)
            
        logger.info(f"Workorders não sincronizadas encontradas: {len(workorders)}")
        
    except PyMongoError as e:
        logger.error(f"Erro ao ler workorders do MongoDB: {e}")
    
    return workorders


async def upsert_workorder(workorder_data: Dict) -> bool:
    """Insere ou atualiza workorder no MongoDB."""
    try:
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
        return True
        
    except PyMongoError as e:
        logger.error(f"Erro ao salvar workorder {workorder_data.get('number')}: {e}")
        return False


async def mark_as_synced(number: int) -> bool:
    """Marca workorder como sincronizada."""
    try:
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
            
    except PyMongoError as e:
        logger.error(f"Erro ao marcar workorder {number} como sincronizada: {e}")
        return False