"""
Tradutor de dados entre formato Cliente e TracOS.
Este módulo implementa as regras de negócio para conversão bidirecional
de dados entre os sistemas Cliente e TracOS, garantindo compliance
com os schemas e tratamento adequado de casos especiais.
"""

from typing import Dict, Optional
from datetime import datetime
from loguru import logger
import json


class DataTranslator:

    def __init__(self):
        logger.info("DataTranslator inicializado.")

    
    VALID_TRACOS_STATUS = {
        "pending", "in_progress", "completed", "on_hold", "cancelled"
    }
    STATUS_PRIORITY_MAP = [
        ("isDone", "completed"),
        ("isCanceled", "cancelled"),
        ("isOnHold", "on_hold"),
        ("isActive", "in_progress"),
        ("isPending", "pending")
    ]
    
    
    def convert_iso_to_datetime(self, date_string: str, field_name: str) -> datetime:

        try:
            normalized_date = date_string.replace("Z", "+00:00")
            parsed_date = datetime.fromisoformat(normalized_date)
            logger.debug(f"Data parseada com sucesso: {field_name} = {date_string}")
            return parsed_date
            
        except (ValueError, AttributeError) as e:
            logger.error(f"Erro ao parsear data do campo '{field_name}': {date_string} - {e}")
            raise ValueError(f"Data inválida no campo '{field_name}': {date_string}")
    
    
    def _determine_tracos_status(self, client_data: Dict) -> str:
        # Verifica flags em ordem de prioridade
        for client_flag, tracos_status in self.STATUS_PRIORITY_MAP:
            if client_data.get(client_flag, False):
                logger.debug(f"Status determinado: {client_flag}=True → {tracos_status}")
                return tracos_status
        
        # Padrão se nenhum flag estiver True
        logger.debug("Nenhum status específico encontrado, usando padrão: pending")
        return "pending"
    
    
    def _validate_required_fields(self, data: Dict, required_fields: list, data_type: str):

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            error_msg = f"Campos obrigatórios ausentes em {data_type}: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise KeyError(error_msg)
        
        logger.debug(f"Validação de campos {data_type} bem-sucedida")

    
    def convert_client_to_tracos(self, client_data: Dict) -> Dict:

        required_fields = ["orderNo", "summary", "creationDate"]
        self._validate_required_fields(client_data, required_fields, "dados do cliente")
    
        status = self._determine_tracos_status(client_data)
        if status not in self.VALID_TRACOS_STATUS:
            error_msg = f"Status inválido gerado: {status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        created_at = self.convert_iso_to_datetime(client_data["creationDate"], "creationDate")
        
        # Data de atualização: usa lastUpdateDate se disponível, senão creationDate
        update_date_str = client_data.get("lastUpdateDate", client_data["creationDate"])
        updated_at = self.convert_iso_to_datetime(update_date_str, "lastUpdateDate/creationDate")
        
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
            tracos_data["deletedAt"] = self.convert_iso_to_datetime(
                client_data["deletedDate"], "deletedDate"
            )

        logger.info(f"Dados do cliente convertidos em dados do TracOS:\n{json.dumps({'Dados do cliente': client_data, 'Dados do TracOS': tracos_data}, indent=2, ensure_ascii=False, default=str)}")
                
        #logger.info(f"Dados do cliente: {client_data} convertidos em dados do TracOs: {tracos_data}.")
        #logger.info(f"Convertido Cliente → TracOS: order {client_data['orderNo']} com status '{status}'")
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



data_translator = DataTranslator()

