import os
from pathlib import Path


class Config:
    """ Configurações centralizadas para o sistema de integração TracOS ↔ Cliente. """
    
    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DATABASE = os.getenv("MONGO_DATABASE", "tractian")
    MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "workorders")
    
    # Diretórios de dados
    DATA_INBOUND_DIR = Path(os.getenv("DATA_INBOUND_DIR", "./data/inbound"))
    DATA_OUTBOUND_DIR = Path(os.getenv("DATA_OUTBOUND_DIR", "./data/outbound"))


# Instância global
config = Config()