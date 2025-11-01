""" Adaptador responsável pelas operações no MongoDB do TracOS. """

import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import (PyMongoError, NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ConnectionFailure, NotPrimaryError, ExecutionTimeout, WTimeoutError)
from config import config
from loguru import logger


class TracosAdapter:
    
    def __init__(self):
        logger.info("Inicializado TracosAdapter...")
        self._mongo_client: Optional[AsyncIOMotorClient] = None
        logger.info("TracosAdapter pronto para operações com o banco MongoDB do TracOS.")

    
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
    
    
    # Exceções que merecem retry (problemas temporários de rede/conexão)
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
                    wait_time = 2 ** attempt  # Backoff exponencial: 1s, 2s, 4s
                    logger.warning(f"Tentativa {attempt + 1} falhou, retry em {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"MongoDB falhou após {max_attempts} tentativas: {e}")
                    raise e
                    
            except PyMongoError as e:
                logger.error(f"MongoDB erro permanente: {e}")
                raise e
            
    
    async def read_unsynced_workorders(self) -> List[Dict]:
        async def _read_unsynced_workorders():
            workorders = []
            collection = await self.get_workorders_collection()
            
            # Busca workorders não sincronizadas
            cursor = collection.find({"isSynced": {"$ne": True}})
            
            async for doc in cursor:
                # Converte ObjectId para string para serialização JSON
                doc["_id"] = str(doc["_id"])
                workorders.append(doc)
            
            logger.info(f"Encontrados {len(workorders)} workorder(s) não sincronizada(s) no TrackOS.")
            return workorders
        
        try:
            return await self._retry_mongo_operation(_read_unsynced_workorders)
        except PyMongoError as e:
            logger.error(f"Erro ao ler workorders não sincronizadas. Detalhes: {e}")
            return []
        
    
    async def upsert_workorder(self, workorder_data: Dict) -> bool:
        async def _upsert_workorder():
            collection = await self.get_workorders_collection()
            
            # Usar 'number' como chave única para identificar workorders
            filter_query = {"number": workorder_data["number"]}
            
            # Adicionar campos de controle de sincronização
            workorder_data_copy = workorder_data.copy()
            workorder_data_copy.update({
                "isSynced": False,
                "updatedAt": datetime.now(timezone.utc)
            })
 
            logger.debug(f"Workorder com number={workorder_data['number']} marcada como não sincronizada no TrackOS. (isSynced=False)")
            
            # Upsert: atualiza se existe, insere se não existe, removendo syncedAt
            result = await collection.update_one(
                filter_query,
                {
                    "$set": workorder_data_copy,
                    "$unset": {"syncedAt": ""}
                },
                upsert=True
            )

            action = "inserida" if result.upserted_id else "atualizada"
            logger.debug(f"Workorder com number={workorder_data['number']} foi {action}.")
            return True
        
        try:
            return await self._retry_mongo_operation(_upsert_workorder)
        except PyMongoError as e:
            logger.error(f"Erro ao salvar workorder {workorder_data.get('number')}: {e}")
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
                logger.debug(f"Workorder com number={number} sincronizada no TrackOS. (isSynced=True).")
                return True
            else:
                logger.warning(f"Workorder com number={number} não encontrada no TrackOS.")
                return False
        
        try:
            return await self._retry_mongo_operation(_mark_workorder_as_synced)
        except PyMongoError as e:
            logger.error(f"Erro ao marcar workorder {number} como sincronizada: {e}")
            return False
        
            




tracos_adapter = TracosAdapter()

