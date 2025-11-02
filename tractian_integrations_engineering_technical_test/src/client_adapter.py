
"""Adapter responsible for I/O operations with client JSON files."""

import json
from typing import List, Dict, Optional
from pathlib import Path
from json import JSONDecodeError
from config import config
from loguru import logger


class ClientAdapter:

    def __init__(self):
        logger.info("ClientAdapter initialized...")
        self.inbound_dir = config.DATA_INBOUND_DIR
        self.outbound_dir = config.DATA_OUTBOUND_DIR
        logger.info("ClientAdapter ready to manage client JSON files.")

    
    def read_inbound_files(self) -> List[Dict]:
        files_data = []
        json_files = list(self.inbound_dir.glob("*.json"))
        if not json_files:
            logger.info(f"No JSON files found in inbound.")
            return files_data
        
        logger.info(f"Starting to read {len(json_files)} workorder(s) from inbound.")
        for json_file in json_files:
            file_data = self._read_single_file(json_file)
            if file_data is not None:
                files_data.append(file_data)
        
        logger.info(f"Inbound directory with {len(files_data)} JSON workorder(s) read.")
        return files_data
    
    
    def _read_single_file(self, file_path: Path) -> Optional[Dict]:
        logger.debug(f"Reading workorder '{file_path.name}'.")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"workorder {file_path.name} read.")
                return data
        
        except FileNotFoundError:
            logger.error(f"File not found: {file_path.name} ")
        except PermissionError:
            logger.error(f"Permission denied to read: {file_path.name}")
        except JSONDecodeError:
            logger.error(f"File contains invalid JSON: {file_path.name}")
        except OSError as e:
            logger.error(f"System error while reading {file_path.name}. Details: {e}")
        except Exception as e:
            logger.error(f"Unexpected error reading {file_path.name}. Details: {e}")
            
        return None
    
    
    def write_outbound_file(self, filename: str, data: Dict) -> bool:
        logger.info(f"Creating workorder='{filename}' in outbound.")
        
        file_path = self.outbound_dir / filename
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Workorder={filename} created successfully.")
            return True
            
        except PermissionError:
            logger.error(f"Permission denied to write {filename} in outbound.")
        except OSError as e:
            logger.error(f"System error while writing {filename} in outbound. Details: {e}")
        except Exception as e:
            logger.error(f"Unexpected error writing {filename} in outbound. Details {e}")
            
        return False    
    

    def validate_client_data(self, data: Dict) -> bool:
        logger.info(f"Validating required fields for workorder with orderNo={data.get('orderNo')}")
        
        missing_fields = []
        required_fields = ["orderNo", "summary", "creationDate"]
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            logger.warning(f"Data is not valid. Missing fields: {', '.join(missing_fields)}.")
            return False
        
        logger.info(f"Data is valid for workorder with orderNo={data.get('orderNo')}.")
        return True

