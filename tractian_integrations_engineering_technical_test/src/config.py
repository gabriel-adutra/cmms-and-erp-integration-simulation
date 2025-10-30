import os
from pathlib import Path
from loguru import logger


class Config:
    """
    Configurações centralizadas do sistema TracOS ↔ Cliente.
    
    Esta classe garante que todas as partes do sistema usem as mesmas
    configurações, carregadas uma única vez das variáveis de ambiente.
    """
    
    _instance = None  # Para garantir uma única instância (Singleton)
    
    def __new__(cls):
        """Garante que só existe uma instância desta classe."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Inicializa as configurações apenas uma vez."""
        if self._initialized:
            return  # Já foi inicializado
            
        # Configurações do MongoDB
        self.MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.MONGO_DATABASE = os.getenv("MONGO_DATABASE", "tractian")
        self.MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "workorders")
        
        # Diretórios de arquivos JSON
        self.DATA_INBOUND_DIR = Path(os.getenv("DATA_INBOUND_DIR", "./data/inbound"))
        self.DATA_OUTBOUND_DIR = Path(os.getenv("DATA_OUTBOUND_DIR", "./data/outbound"))
        
        self._initialized = True
        logger.info("Configurações carregadas com sucesso")


# Instância global - todos os módulos usam esta mesma instância
config = Config()