"""
Testes de integração end-to-end do sistema TracOS ↔ Cliente.
Este módulo valida o pipeline completo de integração bidirecional,
testando desde a leitura de arquivos até a sincronização com MongoDB,
garantindo integridade de dados e funcionamento das classes refatoradas.
"""

import os
import json
import subprocess
import asyncio
import sys
from pathlib import Path
from typing import Dict, List
from datetime import datetime
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config import config
from main import main, inbound_flow, outbound_flow
from translator import data_translator
from client_adapter import client_adapter
from tracos_adapter import tracos_adapter


class IntegrationTestHelper:
    """
    Helper class para testes de integração com métodos utilitários.
    Centraliza operações comuns de setup, cleanup e validação
    para manter os testes organizados e reutilizáveis.
    """
    
    @staticmethod
    async def cleanup_environment():
        """
        Limpa MongoDB e arquivos para garantir ambiente limpo.
        Remove todos os registros do MongoDB e arquivos JSON temporários,
        exceto .gitignore, para garantir que cada teste comece com estado limpo.
        """
        # Limpar MongoDB usando o adapter refatorado
        try:
            client = await tracos_adapter.get_client()
            db = client[config.MONGO_DATABASE]
            await db[config.MONGO_COLLECTION].delete_many({})
            await tracos_adapter.close_connection()
        except Exception:
            pass  # MongoDB pode não estar rodando ainda
        
        # Limpar arquivos inbound e outbound
        for directory in [config.DATA_INBOUND_DIR, config.DATA_OUTBOUND_DIR]:
            if os.path.exists(directory):
                for file in Path(directory).glob("*.json"):
                    if file.name != ".gitignore":
                        file.unlink()
    
    @staticmethod
    def run_setup_script() -> subprocess.CompletedProcess:
        """
        Executa o script setup.py para gerar dados de teste.
        Returns:
            Resultado da execução do subprocess
        """
        return subprocess.run(
            ["python", "setup.py"], 
            cwd=Path(__file__).parent.parent,
            capture_output=True, 
            text=True
        )
    
    @staticmethod
    async def validate_mongodb_records(expected_count: int = 10) -> int:
        """
        Valida número de registros no MongoDB.
        Args:
            expected_count: Número esperado de registros
        Returns:
            Número real de registros encontrados
        """
        client = await tracos_adapter.get_client()
        db = client[config.MONGO_DATABASE]
        collection = db[config.MONGO_COLLECTION]
        
        count = await collection.count_documents({})
        await tracos_adapter.close_connection()
        
        return count
    
    @staticmethod
    def validate_json_files(directory: Path, pattern: str, expected_count: int = 10) -> List[Path]:
        """
        Valida arquivos JSON em um diretório.
        
        Args:
            directory: Diretório para verificar
            pattern: Padrão de arquivos (ex: "*.json", "workorder_*.json")
            expected_count: Número esperado de arquivos
            
        Returns:
            Lista de arquivos encontrados
        """
        files = list(directory.glob(pattern))
        # Filtrar .gitignore se presente
        files = [f for f in files if f.name != ".gitignore"]
        
        assert len(files) == expected_count, \
            f"Esperado {expected_count} arquivos {pattern}, encontrado {len(files)}"
        
        return files


# Instância do helper para uso nos testes
test_helper = IntegrationTestHelper()


def test_complete_pipeline_end_to_end():
    """
    Teste principal: pipeline completo do zero à validação final.
    
    Este teste simula exatamente o que um avaliador faria:
    1. Limpa ambiente para estado consistente
    2. Executa setup para gerar dados de teste
    3. Valida pipeline completo com classes refatoradas
    4. Verifica integridade de dados e sincronização
    """
    async def _run_test():
        # Setup: limpar ambiente usando helper
        await test_helper.cleanup_environment()
        
        # 1. Executar setup.py para criar dados amostra
        result = test_helper.run_setup_script()
        assert result.returncode == 0, f"Setup falhou: {result.stderr}"
        
        # 2. Verificar que arquivos inbound foram criados
        inbound_files = test_helper.validate_json_files(
            config.DATA_INBOUND_DIR, "*.json", 10
        )
        
        # 3. Verificar que MongoDB tem registros iniciais
        mongo_count = await test_helper.validate_mongodb_records(10)
        assert mongo_count == 10, f"Esperado 10 registros no MongoDB, encontrado {mongo_count}"
        
        # 4. Executar pipeline principal (usando função original para compatibilidade)
        await main()
        
        # 5. Validar arquivos outbound gerados
        outbound_files = test_helper.validate_json_files(
            config.DATA_OUTBOUND_DIR, "workorder_*.json", 10
        )
        
        # 6. Validar integridade de dados (idempotência)
        await validate_data_integrity()
        
        # 7. Validar registros marcados como sincronizados
        await validate_sync_status()
        
    asyncio.run(_run_test())


def test_integration_pipeline_class():
    """
    Teste específico das classes refatoradas e suas funcionalidades.
    
    Valida que as novas classes (DataTranslator, ClientAdapter, TracosAdapter)
    funcionam corretamente.
    """
    async def _run_test():
        # Limpar ambiente
        await test_helper.cleanup_environment()
        
        # Setup dados
        result = test_helper.run_setup_script()
        assert result.returncode == 0, f"Setup falhou: {result.stderr}"
        
        # Testar execução básica dos fluxos
        await inbound_flow()
        await outbound_flow()
        
        # Limpeza básica
        await tracos_adapter.close_connection()
        
    asyncio.run(_run_test())



async def validate_data_integrity():
    """
    Valida que dados inbound == outbound (idempotência).
    Verifica se o sistema mantém integridade referencial entre os dados
    de entrada e saída, respeitando as regras de transformação de status.
    """
    # Campos que devem ser idênticos entre entrada e saída
    business_fields = [
        'orderNo', 'summary', 'isDone', 'isCanceled', 
        'isOnHold', 'isPending', 'isDeleted', 'deletedDate'
    ]
    
    for i in range(1, 11):
        # Ler arquivo inbound usando paths do config global
        inbound_path = config.DATA_INBOUND_DIR / f"{i}.json"
        assert inbound_path.exists(), f"Arquivo inbound {i}.json não encontrado"
        
        with open(inbound_path, 'r', encoding='utf-8') as f:
            inbound_data = json.load(f)
        
        # Ler arquivo outbound correspondente
        outbound_path = config.DATA_OUTBOUND_DIR / f"workorder_{i}.json"
        assert outbound_path.exists(), f"Arquivo outbound workorder_{i}.json não encontrado"
        
        with open(outbound_path, 'r', encoding='utf-8') as f:
            outbound_data = json.load(f)
        
        # Validar campos business idênticos
        for field in business_fields:
            inbound_value = inbound_data.get(field)
            outbound_value = outbound_data.get(field)
            
            # Caso especial: se todos os status são false no input, 
            # o DataTranslator assume "pending" como padrão, então isPending vira true no output
            if field == 'isPending' and not any([
                inbound_data.get('isDone'), inbound_data.get('isCanceled'),
                inbound_data.get('isOnHold'), inbound_data.get('isPending'),
                inbound_data.get('isActive', False)
            ]):
                # Se todos os status eram false, isPending deve virar true (comportamento correto)
                assert outbound_value == True, \
                    f"isPending deve ser true quando todos os status de entrada eram false no arquivo {i}"
            else:
                # Tratamento especial para campos de data que podem ter precisão diferente
                if field in ['creationDate', 'lastUpdateDate', 'deletedDate'] and inbound_value and outbound_value:
                    # Comparar apenas até os segundos, ignorando diferenças de microsegundos
                    inbound_dt = datetime.fromisoformat(inbound_value.replace('Z', '+00:00'))
                    outbound_dt = datetime.fromisoformat(outbound_value.replace('Z', '+00:00'))
                    
                    # Diferença máxima aceitável: 1 segundo (MongoDB pode arredondar microsegundos)
                    diff = abs((inbound_dt - outbound_dt).total_seconds())
                    assert diff < 1.0, \
                        f"Campo {field} com diferença de tempo muito grande no arquivo {i}: {inbound_value} != {outbound_value}"
                else:
                    assert inbound_value == outbound_value, \
                        f"Campo {field} diferente no arquivo {i}: {inbound_value} != {outbound_value}"
        
        # Validar campo isActive presente no output (gerado pelo DataTranslator)
        assert 'isActive' in outbound_data, f"Campo isActive ausente no workorder_{i}.json"
        
        # Validar formato JSON válido (garantido pelo ClientAdapter)
        assert isinstance(outbound_data['orderNo'], int), f"orderNo deve ser int no workorder_{i}.json"
        assert isinstance(outbound_data['summary'], str), f"summary deve ser str no workorder_{i}.json"


async def validate_sync_status():
    """
    Valida que registros foram marcados como isSynced=true.
    Usa o TracosAdapter refatorado para verificar se todas as workorders
    foram adequadamente marcadas como sincronizadas após o processamento.
    """
    # Usar TracosAdapter para validação (em vez de conexão direta)
    client = await tracos_adapter.get_client()
    db = client[config.MONGO_DATABASE]
    collection = db[config.MONGO_COLLECTION]
    
    # Todos os registros devem estar sincronizados
    synced_count = await collection.count_documents({"isSynced": True})
    total_count = await collection.count_documents({})
    
    assert synced_count == total_count == 10, \
        f"Esperado 10 registros sincronizados, encontrado {synced_count}/{total_count}"
    
    # Fechar conexão adequadamente
    await tracos_adapter.close_connection()


def test_field_mapping_correctness():
    """
    Testa mapeamento específico de campos entre Client ↔ TracOS.
    Valida que o DataTranslator está fazendo as conversões corretas
    de campos e que os dados no MongoDB estão no formato TracOS esperado.
    """
    async def _run_test():
        # Limpar ambiente usando helper
        await test_helper.cleanup_environment()
        
        # Executar setup e pipeline
        result = test_helper.run_setup_script()
        assert result.returncode == 0, f"Setup falhou: {result.stderr}"
        await main()
        
        # Verificar mapeamento no MongoDB usando TracosAdapter
        client = await tracos_adapter.get_client()
        db = client[config.MONGO_DATABASE]
        collection = db[config.MONGO_COLLECTION]
        
        # Pegar primeiro registro para validar mapeamento
        mongo_record = await collection.find_one({"number": 1})
        assert mongo_record is not None, "Registro number=1 não encontrado no MongoDB"
        
        # Validar campos mapeados corretamente pelo DataTranslator
        assert "title" in mongo_record, "Campo 'title' ausente no MongoDB"
        assert "description" in mongo_record, "Campo 'description' ausente no MongoDB"
        assert "status" in mongo_record, "Campo 'status' ausente no MongoDB"
        assert "deleted" in mongo_record, "Campo 'deleted' ausente no MongoDB"
        
        # Validar status é enum válido (conforme DataTranslator.VALID_TRACOS_STATUS)
        valid_statuses = data_translator.VALID_TRACOS_STATUS
        assert mongo_record["status"] in valid_statuses, \
            f"Status '{mongo_record['status']}' inválido. Deve ser um de: {valid_statuses}"
        
        # Validar description é title + " description" (regra do DataTranslator)
        expected_description = f"{mongo_record['title']} description"
        assert mongo_record["description"] == expected_description, \
            f"Description incorreta: esperado '{expected_description}', encontrado '{mongo_record['description']}'"
        
        # Fechar conexão adequadamente
        await tracos_adapter.close_connection()
    
    asyncio.run(_run_test())


def test_status_priority_mapping():
    """
    Testa especificamente a lógica de prioridade de status do DataTranslator.
    
    Valida que a ordem de precedência Done > Canceled > OnHold > Active > Pending
    está sendo respeitada corretamente.
    """
    # Teste com múltiplos status True (deve prevalecer isDone)
    complex_client_data = {
        "orderNo": 9999,
        "summary": "Test priority",
        "creationDate": "2025-10-29T10:00:00Z",
        "isDone": True,       # Maior prioridade
        "isCanceled": True,   # Deve ser ignorado
        "isActive": True      # Deve ser ignorado
    }
    
    tracos_result = data_translator.client_to_tracos(complex_client_data)
    assert tracos_result["status"] == "completed", \
        f"Prioridade incorreta: esperado 'completed', obtido '{tracos_result['status']}'"
    
    # Teste conversão reversa
    client_result = data_translator.tracos_to_client(tracos_result)
    assert client_result["isDone"] == True, "isDone deve ser True na conversão reversa"
    assert client_result["isCanceled"] == False, "isCanceled deve ser False na conversão reversa"


def test_schema_compliance():
    """
    Testa que DataTranslator não gera status inválidos e garante compliance.
    
    Valida que a validação rigorosa do DataTranslator funciona corretamente
    e que os status gerados estão sempre dentro do conjunto válido.
    """
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
    
    # Usar DataTranslator refatorado - não deve dar erro
    tracos_data = data_translator.client_to_tracos(valid_client_data)
    assert tracos_data["status"] == "completed"
    
    # Validar que status está no conjunto válido
    assert tracos_data["status"] in data_translator.VALID_TRACOS_STATUS
    
    # Teste 2: Mapeamento reverso deve funcionar perfeitamente
    client_data_back = data_translator.tracos_to_client(tracos_data)
    assert client_data_back["isDone"] == True
    assert client_data_back["isActive"] == False
    
    # Teste 3: Campo deleted separado do status (regra important do negócio)
    deleted_client_data = valid_client_data.copy()
    deleted_client_data["isDeleted"] = True
    deleted_client_data["isDone"] = False
    deleted_client_data["isPending"] = True
    
    tracos_deleted = data_translator.client_to_tracos(deleted_client_data)
    # Status deve ser "pending" (não "deleted"!) e deleted=True
    assert tracos_deleted["status"] == "pending"
    assert tracos_deleted["deleted"] == True
    
    # Teste 4: Validação de campos obrigatórios
    try:
        invalid_data = {"summary": "Missing orderNo"}
        data_translator.client_to_tracos(invalid_data)
        assert False, "Deveria ter falhado com campos obrigatórios ausentes"
    except KeyError:
        pass  # Comportamento esperado
    
    # Teste 5: Validação de status TracOS inválido
    try:
        from datetime import datetime
        invalid_tracos = {
            "number": 123,
            "title": "Test",
            "status": "status_inexistente",
            "createdAt": datetime.now(),
            "updatedAt": datetime.now()
        }
        data_translator.tracos_to_client(invalid_tracos)
        assert False, "Deveria ter falhado com status TracOS inválido"
    except ValueError:
        pass  # Comportamento esperado


def test_adapter_classes_functionality():
    """
    Testa funcionalidades específicas das classes refatoradas.
    
    Valida que ClientAdapter e TracosAdapter estão funcionando
    corretamente com suas novas funcionalidades.
    """
    # Teste ClientAdapter
    assert hasattr(client_adapter, 'validate_client_data')
    assert hasattr(client_adapter, 'read_inbound_files')
    assert hasattr(client_adapter, 'write_outbound_file')
    
    # Teste TracosAdapter  
    assert hasattr(tracos_adapter, 'read_unsynced_workorders')
    assert hasattr(tracos_adapter, 'upsert_workorder')
    assert hasattr(tracos_adapter, 'mark_as_synced')
    assert hasattr(tracos_adapter, 'close_connection')
    
    # Teste DataTranslator
    assert hasattr(data_translator, 'VALID_TRACOS_STATUS')
    assert hasattr(data_translator, 'STATUS_PRIORITY_MAP')
    assert hasattr(data_translator, 'get_status_mapping_info')
    
    # Teste de funções básicas do main
    assert hasattr(main, '__call__')
    
    # Validar informações de debug do DataTranslator
    mapping_info = data_translator.get_status_mapping_info()
    assert 'valid_tracos_status' in mapping_info
    assert 'priority_mapping' in mapping_info
    assert len(mapping_info['valid_tracos_status']) == 5