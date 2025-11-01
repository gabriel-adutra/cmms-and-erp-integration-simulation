"""Testes de integração end-to-end do sistema TracOS ↔ Cliente."""

import os
import json
import subprocess
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config import config
from main import main
from tracos_adapter import tracos_adapter

EXPECTED_WORKORDER_COUNT = 10
DATE_FIELDS = ['creationDate', 'lastUpdateDate', 'deletedDate']


class IntegrationTestHelper:
    """Helper para testes de integração: setup, cleanup e validação."""
    
    @staticmethod
    async def cleanup_environment():
        """Limpa MongoDB e arquivos JSON para garantir ambiente limpo."""
        try:
            client = await tracos_adapter.get_mongo_client()
            db = client[config.MONGO_DATABASE]
            await db[config.MONGO_COLLECTION].delete_many({})
            await tracos_adapter.close_connection()
        except Exception:
            pass
        
        for directory in [config.DATA_INBOUND_DIR, config.DATA_OUTBOUND_DIR]:
            if os.path.exists(directory):
                for file in Path(directory).glob("*.json"):
                    if file.name != ".gitignore":
                        file.unlink()
    
    @staticmethod
    def run_setup_script() -> subprocess.CompletedProcess:
        """Executa setup.py para gerar dados de teste."""
        return subprocess.run(
            ["python", "setup.py"], 
            cwd=Path(__file__).parent.parent,
            capture_output=True, 
            text=True
        )
    
    @staticmethod
    def read_json_file(file_path: Path) -> dict:
        """Lê e retorna conteúdo de arquivo JSON."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def compare_datetime_fields(inbound_value: str, outbound_value: str, field: str, file_index: int):
        """Compara campos de data com tolerância de 1 segundo."""
        inbound_dt = datetime.fromisoformat(inbound_value.replace('Z', '+00:00'))
        outbound_dt = datetime.fromisoformat(outbound_value.replace('Z', '+00:00'))
        if inbound_dt.tzinfo is None:
            inbound_dt = inbound_dt.replace(tzinfo=timezone.utc)
        if outbound_dt.tzinfo is None:
            outbound_dt = outbound_dt.replace(tzinfo=timezone.utc)
        
        diff = abs((inbound_dt - outbound_dt).total_seconds())
        assert diff < 1.0, \
            f"Campo {field} com diferença de tempo muito grande no arquivo {file_index}: {inbound_value} != {outbound_value}"


test_helper = IntegrationTestHelper()


def test_complete_pipeline_end_to_end():
    """Teste end-to-end: limpa ambiente, executa setup, roda pipeline e valida resultados."""
    async def _run_test():
        await test_helper.cleanup_environment()
        
        result = test_helper.run_setup_script()
        assert result.returncode == 0, f"Setup falhou: {result.stderr}"
        
        await main()
        
        await validate_data_integrity()
        await validate_sync_status()
        
    asyncio.run(_run_test())


async def validate_data_integrity():
    """Valida que dados inbound == outbound (idempotência)."""
    business_fields = [
        'orderNo', 'summary', 'isDone', 'isCanceled', 
        'isOnHold', 'isPending', 'isDeleted', 'deletedDate'
    ]
    
    for i in range(1, EXPECTED_WORKORDER_COUNT + 1):
        inbound_path = config.DATA_INBOUND_DIR / f"{i}.json"
        outbound_path = config.DATA_OUTBOUND_DIR / f"workorder_{i}.json"
        
        inbound_data = test_helper.read_json_file(inbound_path)
        outbound_data = test_helper.read_json_file(outbound_path)
        
        for field in business_fields:
            inbound_value = inbound_data.get(field)
            outbound_value = outbound_data.get(field)
            
            if field == 'isPending' and not any([
                inbound_data.get('isDone'), inbound_data.get('isCanceled'),
                inbound_data.get('isOnHold'), inbound_data.get('isPending'),
                inbound_data.get('isActive', False)
            ]):
                assert outbound_value == True, \
                    f"isPending deve ser true quando todos os status eram false no arquivo {i}"
            elif field in DATE_FIELDS and inbound_value and outbound_value:
                test_helper.compare_datetime_fields(inbound_value, outbound_value, field, i)
            else:
                assert inbound_value == outbound_value, \
                    f"Campo {field} diferente no arquivo {i}: {inbound_value} != {outbound_value}"
        
        assert 'isActive' in outbound_data, f"Campo isActive ausente no workorder_{i}.json"


async def validate_sync_status():
    """Valida que todos os registros foram marcados como isSynced=true."""
    client = await tracos_adapter.get_mongo_client()
    db = client[config.MONGO_DATABASE]
    collection = db[config.MONGO_COLLECTION]
    
    synced_count = await collection.count_documents({"isSynced": True})
    total_count = await collection.count_documents({})
    
    assert synced_count == total_count == EXPECTED_WORKORDER_COUNT, \
        f"Esperado {EXPECTED_WORKORDER_COUNT} registros sincronizados, encontrado {synced_count}/{total_count}"
    
    await tracos_adapter.close_connection()
