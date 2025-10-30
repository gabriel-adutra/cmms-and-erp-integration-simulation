"""
Adaptador para operações com arquivos JSON do sistema cliente.

Este módulo gerencia todas as operações de entrada e saída de dados
do sistema cliente através de arquivos JSON.
"""

import json
from typing import List, Dict, Optional
from pathlib import Path
from json import JSONDecodeError

from config import config
from loguru import logger


class ClientAdapter:
    """
    Adaptador responsável pelas operações de I/O com arquivos JSON do cliente.
    
    Esta classe centraliza todas as operações de leitura e escrita de arquivos
    JSON, garantindo tratamento consistente de erros e logging estruturado.
    """
    
    def __init__(self):
        """Inicializa o adaptador com as configurações do sistema."""
        self.inbound_dir = config.DATA_INBOUND_DIR
        self.outbound_dir = config.DATA_OUTBOUND_DIR
        logger.info("ClientAdapter inicializado")
    
    def read_inbound_files(self) -> List[Dict]:
        """
        Lê todos os arquivos JSON da pasta inbound.
        
        Returns:
            Lista com os dados de todos os arquivos JSON válidos encontrados.
            Arquivos com erro são logados mas não interrompem o processamento.
        """
        files_data = []
        json_files = list(self.inbound_dir.glob("*.json"))
        
        if not json_files:
            logger.warning("Nenhum arquivo JSON encontrado na pasta inbound")
            return files_data
        
        logger.info(f"Processando {len(json_files)} arquivo(s) JSON")
        
        for json_file in json_files:
            file_data = self._read_single_file(json_file)
            if file_data is not None:
                files_data.append(file_data)
        
        logger.info(f"Total de arquivos processados com sucesso: {len(files_data)}")
        return files_data
    
    def _read_single_file(self, file_path: Path) -> Optional[Dict]:
        """
        Lê um único arquivo JSON com tratamento de erros.
        
        Args:
            file_path: Caminho para o arquivo JSON
            
        Returns:
            Dados do arquivo se bem-sucedido, None em caso de erro
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Arquivo lido com sucesso: {file_path.name}")
                return data
                
        except FileNotFoundError:
            logger.error(f"Arquivo não encontrado: {file_path.name}")
        except PermissionError:
            logger.error(f"Sem permissão para ler arquivo: {file_path.name}")
        except JSONDecodeError as e:
            logger.error(f"JSON inválido em {file_path.name}: {e}")
        except OSError as e:
            logger.error(f"Erro de sistema ao ler {file_path.name}: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao ler {file_path.name}: {e}")
            
        return None
    
    def write_outbound_file(self, filename: str, data: Dict) -> bool:
        """
        Escreve um arquivo JSON na pasta outbound.
        
        Args:
            filename: Nome do arquivo a ser criado
            data: Dados a serem escritos no formato JSON
            
        Returns:
            True se bem-sucedido, False em caso de erro
        """
        file_path = self.outbound_dir / filename
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Arquivo escrito com sucesso: {filename}")
            return True
            
        except PermissionError:
            logger.error(f"Sem permissão para escrever arquivo: {filename}")
        except OSError as e:
            logger.error(f"Erro de sistema ao escrever {filename}: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao escrever {filename}: {e}")
            
        return False
    
    def validate_client_data(self, data: Dict) -> bool:
        """
        Valida se os dados do cliente contêm todos os campos obrigatórios.
        
        Args:
            data: Dicionário com os dados do cliente a serem validados
            
        Returns:
            True se todos os campos obrigatórios estão presentes, False caso contrário
        """
        required_fields = ["orderNo", "summary", "creationDate"]
        missing_fields = []
        
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            logger.warning(f"Campos obrigatórios ausentes: {', '.join(missing_fields)}")
            return False
        
        logger.debug("Validação dos dados do cliente bem-sucedida")
        return True


# Instância global para manter compatibilidade com o código existente
client_adapter = ClientAdapter()

