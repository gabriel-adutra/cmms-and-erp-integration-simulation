"""Centralized configuration for the CMMS ↔ Client integration."""

from pathlib import Path
from loguru import logger
from decouple import config as dconfig


class Config:
    
    _instance = None
    
    def __new__(cls):
        """Ensure a single instance (singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return None

        logger.debug("Initializing CMMS ↔ Client integration configuration.")    
        self.MONGO_URI = dconfig("MONGO_URI", default="mongodb://localhost:27017")
        self.MONGO_DATABASE = dconfig("MONGO_DATABASE", default="cmms_db")
        self.MONGO_COLLECTION = dconfig("MONGO_COLLECTION", default="workorders")
        
        self.DATA_INBOUND_DIR = Path(dconfig("DATA_INBOUND_DIR", default="./data/inbound"))
        self.DATA_OUTBOUND_DIR = Path(dconfig("DATA_OUTBOUND_DIR", default="./data/outbound"))
        
        self._initialized = True
        logger.info("Configuration initialized successfully.")