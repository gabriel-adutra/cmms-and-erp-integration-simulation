
"""
Adaptador responsável pelas operações de I/O com arquivos JSON do cliente.
Esse módulo centraliza todas as operações de leitura e escrita de arquivos
JSON, garantindo tratamento consistente de erros e logging estruturado.
"""

import json
from typing import List, Dict, Optional
from pathlib import Path
from json import JSONDecodeError
from config import config
from loguru import logger


class ClientAdapter:

    def __init__(self):
        logger.info("Inicializado Classe ClientAdapter...")
        self.inbound_dir = config.DATA_INBOUND_DIR
        self.outbound_dir = config.DATA_OUTBOUND_DIR
        logger.info("Classe ClientAdapter inicializada.")

    
    def read_inbound_files(self) -> List[Dict]:
        logger.debug("Entrando na função read_inbound_files()")

        files_data = []
        json_files = list(self.inbound_dir.glob("*.json"))
        if not json_files:
            logger.warning(f"Função read_inbound_files() retornando lista vazia. Nenhum arquivo JSON encontrado.")
            return files_data
        
        logger.info(f"Processando {len(json_files)} arquivo(s) JSON.")
        for json_file in json_files:
            file_data = self._read_single_file(json_file)
            if file_data is not None:
                files_data.append(file_data)
        
        logger.info(f"Função read_inbound_files() retornando {len(files_data)} arquivos válidos.")
        return files_data
    
    
    def _read_single_file(self, file_path: Path) -> Optional[Dict]:
        logger.debug(f"Entrando na função _read_single_file(). Lendo arquivo '{file_path.name}'.")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Função _read_single_file() retornando arquivo {file_path.name} lido.")
                return data
        
        except FileNotFoundError:
            logger.error(f"Função _read_single_file() retornando None - arquivo não encontrado: {file_path.name}")
        except PermissionError:
            logger.error(f"Função _read_single_file() retornando None - sem permissão para ler: {file_path.name}")
        except JSONDecodeError as e:
            logger.error(f"Função _read_single_file() retornando None - JSON inválido em {file_path.name}: {e}")
        except OSError as e:
            logger.error(f"Função _read_single_file() retornando None - erro de sistema: {file_path.name}")
        except Exception as e:
            logger.error(f"Função _read_single_file() retornando None - erro inesperado: {file_path.name}")
            
        return None
    
    
    def write_outbound_file(self, filename: str, data: Dict) -> bool:
        logger.debug(f"Entrando na função write_outbound_file() com parâmetros: filename='{filename}', data com {len(data)} campos")
        
        file_path = self.outbound_dir / filename
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Função write_outbound_file() retornando True - arquivo {filename} criado com sucesso")
            return True
            
        except PermissionError:
            logger.error(f"Função write_outbound_file() retornando False - sem permissão para escrever: {filename}")
        except OSError as e:
            logger.error(f"Função write_outbound_file() retornando False - erro de sistema ao escrever {filename}")
        except Exception as e:
            logger.error(f"Função write_outbound_file() retornando False - erro inesperado ao escrever {filename}")
            
        return False    
    

    def validate_client_data(self, data: Dict) -> bool:
        logger.debug(f"Entrando na função validate_client_data() com parâmetros: {data} para validação de campos obrigatórios.")
        
        missing_fields = []
        required_fields = ["orderNo", "summary", "creationDate"]
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            logger.warning(f"Função validate_client_data() retornando False - campos ausentes: {', '.join(missing_fields)}")
            return False
        
        logger.debug(f"Função validate_client_data() retornando True para orderNo={data.get('orderNo')}")
        return True


# Instância global para manter compatibilidade com o código existente
client_adapter = ClientAdapter()

