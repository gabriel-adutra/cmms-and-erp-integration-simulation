"""
Adaptador para operações com arquivos JSON do sistema cliente.
"""

import json
from typing import List, Dict
from pathlib import Path
from config import config
from loguru import logger


def read_inbound_files() -> List[Dict]:
    """Lê todos os arquivos JSON da pasta inbound."""
    files_data = []
    
    for json_file in config.DATA_INBOUND_DIR.glob("*.json"):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                files_data.append(data)
                logger.info(f"Arquivo lido: {json_file.name}")
        except Exception as e:
            logger.error(f"Erro ao ler {json_file.name}: {e}")
    
    return files_data


def write_outbound_file(filename: str, data: Dict) -> None:
    """Escreve um arquivo JSON na pasta outbound."""
    file_path = config.DATA_OUTBOUND_DIR / filename
    
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Arquivo escrito: {filename}")
    except Exception as e:
        logger.error(f"Erro ao escrever {filename}: {e}")


def validate_client_data(data: Dict) -> bool:
    """Valida campos obrigatórios dos dados do cliente."""
    required_fields = ["orderNo", "summary", "creationDate"]
    
    for field in required_fields:
        if field not in data:
            logger.warning(f"Campo obrigatório ausente: {field}")
            return False
    
    return True