
""" Adaptador responsável pelas operações de I/O com arquivos JSON do cliente. """

import json
from typing import List, Dict, Optional
from pathlib import Path
from json import JSONDecodeError
from config import config
from loguru import logger


class ClientAdapter:

    def __init__(self):
        logger.info("Inicializado ClientAdapter...")
        self.inbound_dir = config.DATA_INBOUND_DIR
        self.outbound_dir = config.DATA_OUTBOUND_DIR
        logger.info("ClientAdapter pronto para gerenciar arquivos JSON do cliente.")

    
    def read_inbound_files(self) -> List[Dict]:
        files_data = []
        json_files = list(self.inbound_dir.glob("*.json"))
        if not json_files:
            logger.warning(f"Nenhum arquivo JSON encontrado.")
            return files_data
        
        logger.info(f"Iniciando leitura de {len(json_files)} workorders(s) do inbound.")
        for json_file in json_files:
            file_data = self._read_single_file(json_file)
            if file_data is not None:
                files_data.append(file_data)
        
        logger.info(f"Diretório inbound com {len(files_data)} workorders(s) JSON lidos.")
        return files_data
    
    
    def _read_single_file(self, file_path: Path) -> Optional[Dict]:
        logger.debug(f"Lendo workorder '{file_path.name}'.")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"workorder {file_path.name} lido.")
                return data
        
        except FileNotFoundError:
            logger.error(f"Arquivo não encontrado: {file_path.name} ")
        except PermissionError:
            logger.error(f"Sem permissão para ler: {file_path.name}")
        except JSONDecodeError as e:
            logger.error(f"Arquivo contém JSON inválido: {file_path.name}")
        except OSError as e:
            logger.error(f"Erro de sistema ao ler {file_path.name}. Detalhes: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao ler {file_path.name}. Detalhes: {e}")
            
        return None
    
    
    def write_outbound_file(self, filename: str, data: Dict) -> bool:
        logger.debug(f"Criando workorder='{filename}' em outbound.")
        
        file_path = self.outbound_dir / filename
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Workorder={filename} criado com sucesso em outbound.")
            return True
            
        except PermissionError:
            logger.error(f"Sem permissão para escrever {filename} em outbound.")
        except OSError as e:
            logger.error(f"Erro de sistema ao escrever {filename} em outbound. Detalhes: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao escrever {filename} em outbound. Detalhes {e}")
            
        return False    
    

    def validate_client_data(self, data: Dict) -> bool:
        logger.info(f"Validando dados obrigatórios do cliente...")
        
        missing_fields = []
        required_fields = ["orderNo", "summary", "creationDate"]
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            logger.warning(f"Os dados não são válidos. Campos ausentes: {', '.join(missing_fields)}.")
            return False
        
        logger.info(f"Os dados são válidos para o workorder de orderNo={data.get('orderNo')}.")
        return True



client_adapter = ClientAdapter()

