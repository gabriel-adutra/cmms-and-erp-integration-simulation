"""
Tradutor de dados entre formato Cliente e TracOS.
"""

from typing import Dict
from datetime import datetime


def client_to_tracos(client_data: Dict) -> Dict:
    """Converte dados do formato Cliente para TracOS."""
    # Mapear status de booleans para enum (independente de deleted)
    status = "pending"  # padrão
    if client_data.get("isDone"):
        status = "completed"
    elif client_data.get("isCanceled"):
        status = "cancelled"
    elif client_data.get("isOnHold"):
        status = "on_hold"
    elif client_data.get("isPending"):
        status = "pending"
    elif client_data.get("isActive"):
        status = "in_progress"
    
    # Validação de segurança - garante schema compliance
    assert status in ("pending", "in_progress", "completed", "on_hold", "cancelled"), f"Status inválido: {status}"
    
    tracos_data = {
        "number": client_data["orderNo"],
        "title": client_data["summary"],
        "status": status,
        "description": f"{client_data['summary']} description",
        "createdAt": datetime.fromisoformat(client_data["creationDate"].replace("Z", "+00:00")),
        "updatedAt": datetime.fromisoformat(client_data.get("lastUpdateDate", client_data["creationDate"]).replace("Z", "+00:00")),
        "deleted": client_data.get("isDeleted", False)
    }
    
    # Adicionar deletedAt se workorder foi deletada
    if client_data.get("isDeleted") and client_data.get("deletedDate"):
        tracos_data["deletedAt"] = datetime.fromisoformat(client_data["deletedDate"].replace("Z", "+00:00"))
    
    return tracos_data


def tracos_to_client(tracos_data: Dict) -> Dict:
    """Converte dados do formato TracOS para Cliente."""
    status = tracos_data["status"]
    
    client_data = {
        "orderNo": tracos_data["number"],
        "summary": tracos_data["title"],
        "creationDate": tracos_data["createdAt"].isoformat(),
        "lastUpdateDate": tracos_data["updatedAt"].isoformat(),
        "isDeleted": tracos_data.get("deleted", False),
        "deletedDate": (
            tracos_data["deletedAt"].isoformat() if tracos_data.get("deletedAt") else None
        ),
        "isDone": status == "completed",
        "isCanceled": status == "cancelled",
        "isOnHold": status == "on_hold",
        "isPending": status == "pending",
        "isActive": status == "in_progress"
    }
    
    return client_data