"""
Tradutor de dados entre formato Cliente e TracOS.

Este módulo implementa as regras de negócio para conversão bidirecional
de dados entre os sistemas Cliente e TracOS, garantindo compliance
com os schemas e tratamento adequado de casos especiais.
"""

from typing import Dict, Optional
from datetime import datetime
from loguru import logger


class DataTranslator:
    """
    Tradutor responsável pela conversão bidirecional Cliente ↔ TracOS.
    
    Esta classe implementa as regras de negócio para mapeamento de campos,
    transformação de status e tratamento de datas, garantindo que os dados
    convertidos estejam em compliance com os schemas de ambos os sistemas.
    """
    
    # Status válidos do TracOS (conforme schema)
    VALID_TRACOS_STATUS = {
        "pending", "in_progress", "completed", "on_hold", "cancelled"
    }
    
    # Mapeamento de prioridade para conversão Cliente → TracOS
    # Ordem de precedência: Done > Canceled > OnHold > Active > Pending (padrão)
    STATUS_PRIORITY_MAP = [
        ("isDone", "completed"),
        ("isCanceled", "cancelled"),
        ("isOnHold", "on_hold"),
        ("isActive", "in_progress"),
        ("isPending", "pending")
    ]
    
    def __init__(self):
        """Inicializa o tradutor de dados."""
        logger.info("DataTranslator inicializado")
    
    def _parse_datetime_safe(self, date_string: str, field_name: str) -> datetime:
        """
        Converte string de data para datetime de forma segura.
        
        Args:
            date_string: String no formato ISO com ou sem 'Z'
            field_name: Nome do campo para logging de erro
            
        Returns:
            Objeto datetime parseado
            
        Raises:
            ValueError: Se a data não puder ser parseada
        """
        try:
            # Normaliza formato ISO: substitui 'Z' por '+00:00' para UTC
            normalized_date = date_string.replace("Z", "+00:00")
            parsed_date = datetime.fromisoformat(normalized_date)
            logger.debug(f"Data parseada com sucesso: {field_name} = {date_string}")
            return parsed_date
            
        except (ValueError, AttributeError) as e:
            logger.error(f"Erro ao parsear data do campo '{field_name}': {date_string} - {e}")
            raise ValueError(f"Data inválida no campo '{field_name}': {date_string}")
    
    def _determine_tracos_status(self, client_data: Dict) -> str:
        """
        Determina o status TracOS baseado nos flags booleanos do cliente.
        
        Aplica ordem de prioridade: Done > Canceled > OnHold > Active > Pending
        
        Args:
            client_data: Dados do cliente contendo flags de status
            
        Returns:
            Status válido do TracOS
        """
        # Verifica flags em ordem de prioridade
        for client_flag, tracos_status in self.STATUS_PRIORITY_MAP:
            if client_data.get(client_flag, False):
                logger.debug(f"Status determinado: {client_flag}=True → {tracos_status}")
                return tracos_status
        
        # Padrão se nenhum flag estiver True
        logger.debug("Nenhum status específico encontrado, usando padrão: pending")
        return "pending"
    
    def _validate_required_fields(self, data: Dict, required_fields: list, data_type: str):
        """
        Valida se todos os campos obrigatórios estão presentes nos dados.
        
        Args:
            data: Dicionário com os dados a serem validados
            required_fields: Lista de campos obrigatórios
            data_type: Tipo de dados (para logging)
            
        Raises:
            KeyError: Se algum campo obrigatório estiver ausente
        """
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            error_msg = f"Campos obrigatórios ausentes em {data_type}: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise KeyError(error_msg)
        
        logger.debug(f"Validação de campos {data_type} bem-sucedida")
    
    def client_to_tracos(self, client_data: Dict) -> Dict:
        """
        Converte dados do formato Cliente para TracOS.
        
        Args:
            client_data: Dados no formato do sistema Cliente
            
        Returns:
            Dados convertidos para o formato TracOS
            
        Raises:
            KeyError: Se campos obrigatórios estiverem ausentes
            ValueError: Se dados estiverem em formato inválido
        """
        # Validar campos obrigatórios do cliente
        required_fields = ["orderNo", "summary", "creationDate"]
        self._validate_required_fields(client_data, required_fields, "dados do cliente")
        
        # Determinar status TracOS baseado nos flags booleanos
        status = self._determine_tracos_status(client_data)
        
        # Validação de segurança - garante schema compliance
        if status not in self.VALID_TRACOS_STATUS:
            error_msg = f"Status inválido gerado: {status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Parsing seguro de datas
        created_at = self._parse_datetime_safe(client_data["creationDate"], "creationDate")
        
        # Data de atualização: usa lastUpdateDate se disponível, senão creationDate
        update_date_str = client_data.get("lastUpdateDate", client_data["creationDate"])
        updated_at = self._parse_datetime_safe(update_date_str, "lastUpdateDate/creationDate")
        
        # Construir dados TracOS
        tracos_data = {
            "number": client_data["orderNo"],
            "title": client_data["summary"],
            "status": status,
            "description": f"{client_data['summary']} description",
            "createdAt": created_at,
            "updatedAt": updated_at,
            "deleted": client_data.get("isDeleted", False)
        }
        
        # Adicionar deletedAt se workorder foi deletada e tem data de deleção
        if client_data.get("isDeleted") and client_data.get("deletedDate"):
            tracos_data["deletedAt"] = self._parse_datetime_safe(
                client_data["deletedDate"], "deletedDate"
            )
        
        logger.info(f"Convertido Cliente → TracOS: order {client_data['orderNo']} com status '{status}'")
        return tracos_data
    
    def tracos_to_client(self, tracos_data: Dict) -> Dict:
        """
        Converte dados do formato TracOS para Cliente.
        
        Args:
            tracos_data: Dados no formato do sistema TracOS
            
        Returns:
            Dados convertidos para o formato Cliente
            
        Raises:
            KeyError: Se campos obrigatórios estiverem ausentes
            ValueError: Se dados estiverem em formato inválido
        """
        # Validar campos obrigatórios do TracOS
        required_fields = ["number", "title", "status", "createdAt", "updatedAt"]
        self._validate_required_fields(tracos_data, required_fields, "dados do TracOS")
        
        status = tracos_data["status"]
        
        # Validar se status é válido
        if status not in self.VALID_TRACOS_STATUS:
            error_msg = f"Status TracOS inválido: {status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Converter datas para formato ISO string
        try:
            creation_date = tracos_data["createdAt"].isoformat()
            update_date = tracos_data["updatedAt"].isoformat()
        except AttributeError as e:
            logger.error(f"Erro ao converter datas para ISO: {e}")
            raise ValueError(f"Datas do TracOS devem ser objetos datetime: {e}")
        
        # Construir dados do cliente com flags booleanos baseados no status
        client_data = {
            "orderNo": tracos_data["number"],
            "summary": tracos_data["title"],
            "creationDate": creation_date,
            "lastUpdateDate": update_date,
            "isDeleted": tracos_data.get("deleted", False),
            "deletedDate": (
                tracos_data["deletedAt"].isoformat() 
                if tracos_data.get("deletedAt") else None
            ),
            # Flags booleanos baseados no status TracOS
            "isDone": status == "completed",
            "isCanceled": status == "cancelled",
            "isOnHold": status == "on_hold",
            "isPending": status == "pending",
            "isActive": status == "in_progress"
        }
        
        logger.info(f"Convertido TracOS → Cliente: order {tracos_data['number']} com status '{status}'")
        return client_data
    
    def get_status_mapping_info(self) -> Dict:
        """
        Retorna informações sobre o mapeamento de status para debugging.
        
        Returns:
            Dicionário com informações de mapeamento
        """
        return {
            "valid_tracos_status": list(self.VALID_TRACOS_STATUS),
            "priority_mapping": self.STATUS_PRIORITY_MAP,
            "description": "Ordem de prioridade: Done > Canceled > OnHold > Active > Pending (padrão)"
        }


# Instância global para manter compatibilidade com o código existente
data_translator = DataTranslator()

