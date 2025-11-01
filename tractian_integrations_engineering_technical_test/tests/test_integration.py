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
from datetime import datetime, timezone
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
            client = await tracos_adapter.get_mongo_client()
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
        client = await tracos_adapter.get_mongo_client()
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
                    # Normalizar para timezone-aware (UTC) se necessário
                    if inbound_dt.tzinfo is None:
                        inbound_dt = inbound_dt.replace(tzinfo=timezone.utc)
                    if outbound_dt.tzinfo is None:
                        outbound_dt = outbound_dt.replace(tzinfo=timezone.utc)
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
    client = await tracos_adapter.get_mongo_client()
    db = client[config.MONGO_DATABASE]
    collection = db[config.MONGO_COLLECTION]
    
    # Todos os registros devem estar sincronizados
    synced_count = await collection.count_documents({"isSynced": True})
    total_count = await collection.count_documents({})
    
    assert synced_count == total_count == 10, \
        f"Esperado 10 registros sincronizados, encontrado {synced_count}/{total_count}"
    
    # Fechar conexão adequadamente
    await tracos_adapter.close_connection()
