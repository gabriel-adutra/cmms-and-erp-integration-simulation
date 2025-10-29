"""
Testes de integração end-to-end do sistema TracOS ↔ Cliente.
Valida o pipeline completo: inbound → TracOS → outbound com integridade de dados.
"""

import os
import json
import subprocess
import asyncio
import sys
from pathlib import Path
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

# Adicionar src ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from main import main
from translator import client_to_tracos, tracos_to_client


async def cleanup_environment():
    """Limpa MongoDB e arquivos para ambiente limpo."""
    config = Config()
    
    # Limpar MongoDB
    try:
        client = AsyncIOMotorClient(config.MONGO_URI)
        db = client[config.MONGO_DATABASE]
        await db[config.MONGO_COLLECTION].delete_many({})
        client.close()
    except Exception:
        pass  # MongoDB pode não estar rodando ainda
    
    # Limpar arquivos inbound e outbound
    for directory in [config.DATA_INBOUND_DIR, config.DATA_OUTBOUND_DIR]:
        if os.path.exists(directory):
            for file in Path(directory).glob("*.json"):
                if file.name != ".gitignore":
                    file.unlink()


def test_complete_pipeline_end_to_end():
    """
    Teste principal: pipeline completo do zero à validação final.
    Simula exatamente o que um avaliador faria.
    """
    async def _run_test():
        config = Config()
        
        # Setup: limpar ambiente
        await cleanup_environment()
        
        # 1. Executar setup.py para criar dados amostra
        result = subprocess.run(
            ["python", "setup.py"], 
            cwd=Path(__file__).parent.parent,
            capture_output=True, 
            text=True
        )
        assert result.returncode == 0, f"Setup falhou: {result.stderr}"
        
        # 2. Verificar que arquivos inbound foram criados
        inbound_files = list(Path(config.DATA_INBOUND_DIR).glob("*.json"))
        inbound_files = [f for f in inbound_files if f.name != ".gitignore"]
        assert len(inbound_files) == 10, f"Esperado 10 arquivos inbound, encontrado {len(inbound_files)}"
        
        # 3. Verificar que MongoDB tem registros iniciais
        client = AsyncIOMotorClient(config.MONGO_URI)
        db = client[config.MONGO_DATABASE]
        collection = db[config.MONGO_COLLECTION]
        
        mongo_count = await collection.count_documents({})
        assert mongo_count == 10, f"Esperado 10 registros no MongoDB, encontrado {mongo_count}"
        client.close()
        
        # 4. Executar pipeline principal
        await main()
        
        # 5. Validar arquivos outbound gerados
        outbound_files = list(Path(config.DATA_OUTBOUND_DIR).glob("workorder_*.json"))
        assert len(outbound_files) == 10, f"Esperado 10 arquivos outbound, encontrado {len(outbound_files)}"
        
        # 6. Validar integridade de dados (idempotência)
        await validate_data_integrity()
        
        # 7. Validar registros marcados como sincronizados
        await validate_sync_status()
    
    asyncio.run(_run_test())


async def validate_data_integrity():
    """Valida que dados inbound == outbound (idempotência)."""
    config = Config()
    
    # Campos que devem ser idênticos
    business_fields = [
        'orderNo', 'summary', 'isDone', 'isCanceled', 
        'isOnHold', 'isPending', 'isDeleted', 'deletedDate'
    ]
    
    for i in range(1, 11):
        # Ler arquivo inbound
        inbound_path = Path(config.DATA_INBOUND_DIR) / f"{i}.json"
        assert inbound_path.exists(), f"Arquivo inbound {i}.json não encontrado"
        
        with open(inbound_path) as f:
            inbound_data = json.load(f)
        
        # Ler arquivo outbound correspondente
        outbound_path = Path(config.DATA_OUTBOUND_DIR) / f"workorder_{i}.json"
        assert outbound_path.exists(), f"Arquivo outbound workorder_{i}.json não encontrado"
        
        with open(outbound_path) as f:
            outbound_data = json.load(f)
        
        # Validar campos business idênticos
        for field in business_fields:
            inbound_value = inbound_data.get(field)
            outbound_value = outbound_data.get(field)
            
            # Caso especial: se todos os status são false no input, 
            # o sistema assume "pending" como padrão, então isPending vira true no output
            if field == 'isPending' and not any([
                inbound_data.get('isDone'), inbound_data.get('isCanceled'),
                inbound_data.get('isOnHold'), inbound_data.get('isPending'),
                inbound_data.get('isActive', False)
            ]):
                # Se todos os status eram false, isPending deve virar true (comportamento correto)
                assert outbound_value == True, \
                    f"isPending deve ser true quando todos os status de entrada eram false no arquivo {i}"
            else:
                assert inbound_value == outbound_value, \
                    f"Campo {field} diferente no arquivo {i}: {inbound_value} != {outbound_value}"
        
        # Validar campo isActive presente no output
        assert 'isActive' in outbound_data, f"Campo isActive ausente no workorder_{i}.json"
        
        # Validar formato JSON válido
        assert isinstance(outbound_data['orderNo'], int), f"orderNo deve ser int no workorder_{i}.json"
        assert isinstance(outbound_data['summary'], str), f"summary deve ser str no workorder_{i}.json"


async def validate_sync_status():
    """Valida que registros foram marcados como isSynced=true."""
    config = Config()
    
    client = AsyncIOMotorClient(config.MONGO_URI)
    db = client[config.MONGO_DATABASE]
    collection = db[config.MONGO_COLLECTION]
    
    # Todos os registros devem estar sincronizados
    synced_count = await collection.count_documents({"isSynced": True})
    total_count = await collection.count_documents({})
    
    assert synced_count == total_count == 10, \
        f"Esperado 10 registros sincronizados, encontrado {synced_count}/{total_count}"
    
    client.close()


def test_field_mapping_correctness():
    """Testa mapeamento específico de campos entre Client ↔ TracOS."""
    async def _run_test():
        config = Config()
        
        # Limpar ambiente
        await cleanup_environment()
        
        # Executar setup e pipeline
        subprocess.run(["python", "setup.py"], cwd=Path(__file__).parent.parent, check=True)
        await main()
        
        # Verificar mapeamento no MongoDB
        client = AsyncIOMotorClient(config.MONGO_URI)
        db = client[config.MONGO_DATABASE]
        collection = db[config.MONGO_COLLECTION]
        
        # Pegar primeiro registro para validar mapeamento
        mongo_record = await collection.find_one({"number": 1})
        assert mongo_record is not None, "Registro number=1 não encontrado no MongoDB"
        
        # Validar campos mapeados corretamente
        assert "title" in mongo_record, "Campo 'title' ausente no MongoDB"
        assert "description" in mongo_record, "Campo 'description' ausente no MongoDB"
        assert "status" in mongo_record, "Campo 'status' ausente no MongoDB"
        assert "deleted" in mongo_record, "Campo 'deleted' ausente no MongoDB"
        
        # Validar status é enum válido
        valid_statuses = ["pending", "in_progress", "completed", "on_hold", "cancelled"]
        assert mongo_record["status"] in valid_statuses, \
            f"Status '{mongo_record['status']}' inválido. Deve ser um de: {valid_statuses}"
        
        # Validar description é title + " description"
        expected_description = f"{mongo_record['title']} description"
        assert mongo_record["description"] == expected_description, \
            f"Description incorreta: esperado '{expected_description}', encontrado '{mongo_record['description']}'"
        
        client.close()
    
    asyncio.run(_run_test())


def test_schema_compliance():
    """Testa que translator não gera status inválidos (assert funciona)."""
    # Teste 1: Status válidos não devem dar erro
    valid_client_data = {
        "orderNo": 999,
        "summary": "Test workorder",
        "creationDate": "2025-10-29T10:00:00+00:00",
        "isDone": True,  # Status válido
        "isCanceled": False,
        "isOnHold": False,
        "isPending": False,
        "isActive": False,
        "isDeleted": False
    }
    
    # Não deve dar erro
    tracos_data = client_to_tracos(valid_client_data)
    assert tracos_data["status"] == "completed"
    
    # Teste 2: Mapeamento reverso deve funcionar
    client_data_back = tracos_to_client(tracos_data)
    assert client_data_back["isDone"] == True
    assert client_data_back["isActive"] == False
    
    # Teste 3: Campo deleted separado do status
    deleted_client_data = valid_client_data.copy()
    deleted_client_data["isDeleted"] = True
    deleted_client_data["isDone"] = False
    deleted_client_data["isPending"] = True
    
    tracos_deleted = client_to_tracos(deleted_client_data)
    # Status deve ser "pending" (não "deleted"!) e deleted=True
    assert tracos_deleted["status"] == "pending"
    assert tracos_deleted["deleted"] == True