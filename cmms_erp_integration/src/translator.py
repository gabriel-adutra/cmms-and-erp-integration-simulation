"""
Data translator between Client and CMMS formats.
This module implements business rules for bidirectional conversion
between Client and CMMS systems, ensuring schema compliance and
proper handling of special cases.
"""

from typing import Dict
from datetime import datetime, timezone
from loguru import logger
import json


class DataTranslator:

    def __init__(self):
        logger.info("DataTranslator ready for data conversion (Client ↔ CMMS).")

    
    VALID_CMMS_STATUS = {
        "pending", "in_progress", "completed", "on_hold", "cancelled", "deleted"
    }
    CLIENT_TO_CMMS_STATUS_MAP = [
        ("isDeleted", "deleted"),
        ("isDone", "completed"),
        ("isCanceled", "cancelled"),
        ("isOnHold", "on_hold"),
        ("isPending", "pending"),
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
    
    
    def _determine_cmms_status(self, client_data: Dict) -> str:
        # Check flags in priority order
        for client_flag, cmms_status in self.CLIENT_TO_CMMS_STATUS_MAP:
            if client_data.get(client_flag, False):
                logger.debug(f"Status determined: {client_flag}=True → {cmms_status}")
                return cmms_status
        
        # Default if no flag is True: in_progress
        logger.debug("No specific status found. Using default: in_progress")
        return "in_progress"
    
    
    def _validate_required_fields(self, data: Dict, required_fields: list, data_type: str):

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            error_msg = f"Missing required fields in {data_type}: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise KeyError(error_msg)

    
    def convert_client_to_cmms(self, client_data: Dict) -> Dict:

        required_fields = ["orderNo", "summary", "creationDate"]
        self._validate_required_fields(client_data, required_fields, "client data")
    
        status = self._determine_cmms_status(client_data)
        if status not in self.VALID_CMMS_STATUS:
            error_msg = f"Invalid status generated: {status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        created_at = self.convert_iso_to_datetime(client_data["creationDate"], "creationDate")
        
        # Update date: use lastUpdateDate if available, otherwise creationDate
        update_date_str = client_data.get("lastUpdateDate", client_data["creationDate"])
        updated_at = self.convert_iso_to_datetime(update_date_str, "lastUpdateDate/creationDate")
        
        # Build CMMS data
        cmms_data = {
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
            cmms_data["deletedAt"] = self.convert_iso_to_datetime(
                client_data["deletedDate"], "deletedDate"
            )

        logger.debug(
            f"Client data converted to CMMS data for workorder with orderNo={client_data['orderNo']}:\n"
            f"{json.dumps({'Client data': client_data, 'CMMS data': cmms_data}, indent=2, ensure_ascii=False, default=str)}"
        )
                
        return cmms_data
    
    
    def convert_cmms_to_client(self, cmms_data: Dict) -> Dict:
        
        required_fields = ["number", "title", "status", "createdAt", "updatedAt"]
        self._validate_required_fields(cmms_data, required_fields, "CMMS data")
        
        status = cmms_data["status"]
        if status not in self.VALID_CMMS_STATUS:
            error_msg = f"Invalid CMMS status: {status}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Convert datetimes to ISO strings with explicit UTC offset (+00:00)
        try:
            created_dt = cmms_data["createdAt"]
            updated_dt = cmms_data["updatedAt"]

            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)

            creation_date = created_dt.isoformat()
            update_date = updated_dt.isoformat()
        except AttributeError as e:
            logger.error(f"Error converting datetimes to ISO: {e}")
            raise ValueError(f"CMMS datetimes must be datetime objects: {e}")
        
        # Build client data with boolean flags based on CMMS status
        client_data = {
            "orderNo": cmms_data["number"],
            "summary": cmms_data["title"],
            "creationDate": creation_date,
            "lastUpdateDate": update_date,
            "deletedDate": (
                cmms_data["deletedAt"].isoformat() 
                if cmms_data.get("deletedAt") else None
            ),
            # Boolean flags - always return the 5 basic fields (client always sends them)
            "isDone": status == "completed",
            "isCanceled": status == "cancelled",
            "isOnHold": status == "on_hold",
            "isPending": status == "pending",
            "isDeleted": status == "deleted"
        }
        
        logger.debug(
            f"CMMS data converted to Client data for workorder with number={cmms_data['number']}:\n"
            f"{json.dumps({'CMMS data': cmms_data, 'Client data': client_data}, indent=2, ensure_ascii=False, default=str)}"
        )
        
        return client_data

 

