"""
Data translator between Client and TracOS formats.
This module implements business rules for bidirectional conversion
between Client and TracOS systems, ensuring schema compliance and
proper handling of special cases.
"""

from typing import Dict
from datetime import datetime, timezone
from loguru import logger
import json


class DataTranslator:

    def __init__(self):
        logger.info("DataTranslator ready for data conversion (Client ↔ TracOS).")

    
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
            logger.debug(f"Successfully parsed date: {field_name} = {date_string}")
            return parsed_date
            
        except (ValueError, AttributeError) as e:
            logger.error(f"Error parsing date for field '{field_name}': {date_string}. Details: {e}")
            raise ValueError(f"Invalid date in field '{field_name}': {date_string}")
    
    
    def _determine_tracos_status(self, client_data: Dict) -> str:
        # Check flags in priority order
        for client_flag, tracos_status in self.STATUS_PRIORITY_MAP:
            if client_data.get(client_flag, False):
                logger.debug(f"Status determined: {client_flag}=True → {tracos_status}")
                return tracos_status
        
        # Default if no flag is True
        logger.debug("No specific status found. Using default: pending")
        return "pending"
    
    
    def _validate_required_fields(self, data: Dict, required_fields: list, data_type: str):

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            error_msg = f"Missing required fields in {data_type}: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise KeyError(error_msg)

    
    def convert_client_to_tracos(self, client_data: Dict) -> Dict:

        required_fields = ["orderNo", "summary", "creationDate"]
        self._validate_required_fields(client_data, required_fields, "client data")
    
        status = self._determine_tracos_status(client_data)
        if status not in self.VALID_TRACOS_STATUS:
            error_msg = f"Invalid status generated: {status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        created_at = self.convert_iso_to_datetime(client_data["creationDate"], "creationDate")
        
        # Update date: use lastUpdateDate if available, otherwise creationDate
        update_date_str = client_data.get("lastUpdateDate", client_data["creationDate"])
        updated_at = self.convert_iso_to_datetime(update_date_str, "lastUpdateDate/creationDate")
        
        # Build TracOS data
        tracos_data = {
            "number": client_data["orderNo"],
            "title": client_data["summary"],
            "status": status,
            "description": f"{client_data['summary']} description",
            "createdAt": created_at,
            "updatedAt": updated_at,
            "deleted": client_data.get("isDeleted", False)
        }
        
        # Add deletedAt if the workorder was deleted and has a deletion date
        if client_data.get("isDeleted") and client_data.get("deletedDate"):
            tracos_data["deletedAt"] = self.convert_iso_to_datetime(
                client_data["deletedDate"], "deletedDate"
            )

        logger.debug(
            f"Client data converted to TracOS data for workorder with orderNo={client_data['orderNo']}:\n"
            f"{json.dumps({'Client data': client_data, 'TracOS data': tracos_data}, indent=2, ensure_ascii=False, default=str)}"
        )
                
        return tracos_data
    
    
    def convert_tracos_to_client(self, tracos_data: Dict) -> Dict:
        
        required_fields = ["number", "title", "status", "createdAt", "updatedAt"]
        self._validate_required_fields(tracos_data, required_fields, "TracOS data")
        
        status = tracos_data["status"]
        if status not in self.VALID_TRACOS_STATUS:
            error_msg = f"Invalid TracOS status: {status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Convert datetimes to ISO strings with explicit UTC offset (+00:00)
        try:
            created_dt = tracos_data["createdAt"]
            updated_dt = tracos_data["updatedAt"]

            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)

            creation_date = created_dt.isoformat()
            update_date = updated_dt.isoformat()
        except AttributeError as e:
            logger.error(f"Error converting datetimes to ISO: {e}")
            raise ValueError(f"TracOS datetimes must be datetime objects: {e}")
        
        # Build client data with boolean flags based on TracOS status
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
            # Boolean flags based on TracOS status
            "isDone": status == "completed",
            "isCanceled": status == "cancelled",
            "isOnHold": status == "on_hold",
            "isPending": status == "pending",
            "isActive": status == "in_progress"
        }
        
        logger.debug(
            f"TracOS data converted to Client data for workorder with number={tracos_data['number']}:\n"
            f"{json.dumps({'TracOS data': tracos_data, 'Client data': client_data}, indent=2, ensure_ascii=False, default=str)}"
        )
        
        return client_data



data_translator = DataTranslator()

