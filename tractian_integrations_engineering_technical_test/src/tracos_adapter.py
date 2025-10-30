"""
Adaptador para operações MongoDB do sistema TracOS.

Este módulo gerencia todas as operações assíncronas com o banco de dados
MongoDB, incluindo conexões, operações CRUD e sincronização de workorders.
"""

import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import (
    PyMongoError, NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError,
    ConnectionFailure, NotPrimaryError, ExecutionTimeout, WTimeoutError
)

from .config import config
from loguru import logger


class TracosAdapter:
    """
    Adaptador responsável pelas operações assíncronas com MongoDB do TracOS.
    
    Esta classe gerencia conexões com o banco de dados, operações CRUD
    de workorders e implementa retry automático para falhas temporárias.
    """
    
    # Exceções que merecem retry (problemas temporários de rede/conexão)
    RETRIABLE_ERRORS = (
        NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError,
        ConnectionFailure, NotPrimaryError, ExecutionTimeout, WTimeoutError
    )
    
    def __init__(self):
        """Inicializa o adaptador TracOS."""
        self._client: Optional[AsyncIOMotorClient] = None
        logger.info("TracosAdapter inicializado")
    
    async def get_client(self) -> AsyncIOMotorClient:
        """
        Obtém o cliente MongoDB reutilizando a conexão quando possível.
        
        Returns:
            Cliente MongoDB configurado e conectado
        """
        if self._client is None:
            self._client = AsyncIOMotorClient(config.MONGO_URI)
            logger.debug("Nova conexão MongoDB estabelecida")
        return self._client
    
    async def get_collection(self) -> AsyncIOMotorCollection:
        """
        Obtém a collection de workorders.
        
        Returns:
            Collection MongoDB configurada para workorders
        """
        client = await self.get_client()
        db = client[config.MONGO_DATABASE]
        return db[config.MONGO_COLLECTION]
    
    async def _retry_mongo_operation(self, operation_func, *args, **kwargs):
        """
        Executa operação MongoDB com retry automático para falhas temporárias.
        
        Args:
            operation_func: Função assíncrona a ser executada
            *args, **kwargs: Argumentos para a função
            
        Returns:
            Resultado da operação se bem-sucedida
            
        Raises:
            PyMongoError: Se a operação falhar após todas as tentativas
        """
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                return await operation_func(*args, **kwargs)
                
            except self.RETRIABLE_ERRORS as e:
                if attempt < max_attempts - 1:
                    wait_time = 2 ** attempt  # Backoff exponencial: 1s, 2s, 4s
                    logger.warning(f"Tentativa {attempt + 1} falhou, tentando novamente em {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Operação falhou após {max_attempts} tentativas: {e}")
                    raise e
                    
            except PyMongoError as e:
                # Erro permanente - não vale a pena tentar novamente
                logger.error(f"Erro permanente do MongoDB: {e}")
                raise e
    
    async def read_unsynced_workorders(self) -> List[Dict]:
        """
        Lê todas as workorders que ainda não foram sincronizadas.
        
        Returns:
            Lista de workorders com isSynced=false ou ausente
        """
        async def _read_operation():
            workorders = []
            collection = await self.get_collection()
            
            # Busca workorders não sincronizadas
            cursor = collection.find({"isSynced": {"$ne": True}})
            
            async for doc in cursor:
                # Converte ObjectId para string para serialização JSON
                doc["_id"] = str(doc["_id"])
                workorders.append(doc)
            
            logger.info(f"Encontradas {len(workorders)} workorder(s) não sincronizada(s)")
            return workorders
        
        try:
            return await self._retry_mongo_operation(_read_operation)
        except PyMongoError as e:
            logger.error(f"Falha ao ler workorders não sincronizadas: {e}")
            return []
    
    async def upsert_workorder(self, workorder_data: Dict) -> bool:
        """
        Insere uma nova workorder ou atualiza uma existente.
        
        Args:
            workorder_data: Dados da workorder a ser inserida/atualizada
            
        Returns:
            True se a operação foi bem-sucedida, False caso contrário
        """
        async def _upsert_operation():
            collection = await self.get_collection()
            
            # Usar 'number' como chave única para identificar workorders
            filter_query = {"number": workorder_data["number"]}
            
            # Adicionar campos de controle de sincronização
            workorder_data_copy = workorder_data.copy()
            workorder_data_copy.update({
                "isSynced": False,
                "updatedAt": datetime.now(timezone.utc)
            })
            
            # Upsert: atualiza se existe, insere se não existe
            result = await collection.update_one(
                filter_query,
                {"$set": workorder_data_copy},
                upsert=True
            )
            
            action = "inserida" if result.upserted_id else "atualizada"
            logger.info(f"Workorder {workorder_data['number']} {action} com sucesso")
            return True
        
        try:
            return await self._retry_mongo_operation(_upsert_operation)
        except PyMongoError as e:
            logger.error(f"Falha ao salvar workorder {workorder_data.get('number')}: {e}")
            return False
    
    async def mark_as_synced(self, number: int) -> bool:
        """
        Marca uma workorder como sincronizada após processamento bem-sucedido.
        
        Args:
            number: Número identificador da workorder
            
        Returns:
            True se marcada com sucesso, False se não encontrada ou erro
        """
        async def _mark_operation():
            collection = await self.get_collection()
            
            # Atualiza o status de sincronização
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
            return await self._retry_mongo_operation(_mark_operation)
        except PyMongoError as e:
            logger.error(f"Falha ao marcar workorder {number} como sincronizada: {e}")
            return False
    
    async def close_connection(self):
        """
        Fecha a conexão com MongoDB de forma limpa.
        
        Deve ser chamado ao final do processamento para liberar recursos.
        """
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Conexão MongoDB fechada")


# Instância global para manter compatibilidade com o código existente
tracos_adapter = TracosAdapter()

# Funções de compatibilidade (mantêm a interface original)
async def read_unsynced_workorders() -> List[Dict]:
    """Função de compatibilidade - usa a instância global do TracosAdapter."""
    return await tracos_adapter.read_unsynced_workorders()

async def upsert_workorder(workorder_data: Dict) -> bool:
    """Função de compatibilidade - usa a instância global do TracosAdapter."""
    return await tracos_adapter.upsert_workorder(workorder_data)

async def mark_as_synced(number: int) -> bool:
    """Função de compatibilidade - usa a instância global do TracosAdapter."""
    return await tracos_adapter.mark_as_synced(number)

# Funções auxiliares mantidas para compatibilidade
async def get_mongo_client() -> AsyncIOMotorClient:
    """Função de compatibilidade - obtém cliente via instância global."""
    return await tracos_adapter.get_client()

async def get_collection() -> AsyncIOMotorCollection:
    """Função de compatibilidade - obtém collection via instância global."""
    return await tracos_adapter.get_collection()