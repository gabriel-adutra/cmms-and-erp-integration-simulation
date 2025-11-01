"""Configurações centralizadas do sistema TracOS ↔ Cliente."""

import os
from pathlib import Path
from loguru import logger


class Config:
    
    _instance = None
    
    def __new__(cls):
        """Garante instância única (singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return None

        logger.debug("Inicializando configurações de integração TracOS ↔ Cliente.")    
        self.MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.MONGO_DATABASE = os.getenv("MONGO_DATABASE", "tractian")
        self.MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "workorders")
        
        self.DATA_INBOUND_DIR = Path(os.getenv("DATA_INBOUND_DIR", "./data/inbound"))
        self.DATA_OUTBOUND_DIR = Path(os.getenv("DATA_OUTBOUND_DIR", "./data/outbound"))
        
        self._initialized = True
        logger.info("Configurações inicializadas com sucesso.")


config = Config()