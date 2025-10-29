"""
Tradutor de dados entre formato Cliente e TracOS.
"""

from typing import Dict
from datetime import datetime


def client_to_tracos(client_data: Dict) -> Dict:
    """Converte dados do formato Cliente para TracOS."""
    # Mapear status de booleans para enum
    status = "pending"  # padrão
    if client_data.get("isDone"):
        status = "completed"
    elif client_data.get("isCanceled"):
        status = "cancelled"
    elif client_data.get("isOnHold"):
        status = "on_hold"
    elif client_data.get("isPending"):
        status = "pending"
    
    tracos_data = {
        "number": client_data["orderNo"],
        "title": client_data["summary"],
        "status": status,
        "description": f"{client_data['summary']} description",
        "createdAt": datetime.fromisoformat(client_data["creationDate"].replace("Z", "+00:00")),
        "updatedAt": datetime.fromisoformat(client_data.get("lastUpdateDate", client_data["creationDate"]).replace("Z", "+00:00")),
        "deleted": client_data.get("isDeleted", False)
    }
    
    return tracos_data


def tracos_to_client(tracos_data: Dict) -> Dict:
    """Converte dados do formato TracOS para Cliente."""
    # Mapear enum status para booleans
    client_data = {
        "orderNo": tracos_data["number"],
        "summary": tracos_data["title"],
        "creationDate": tracos_data["createdAt"].isoformat(),
        "lastUpdateDate": tracos_data["updatedAt"].isoformat(),
        "isDeleted": tracos_data.get("deleted", False),
        "isDone": tracos_data["status"] == "completed",
        "isCanceled": tracos_data["status"] == "cancelled", 
        "isOnHold": tracos_data["status"] == "on_hold",
        "isPending": tracos_data["status"] == "pending"
    }
    
    return client_data