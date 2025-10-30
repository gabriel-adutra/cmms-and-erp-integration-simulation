"""
Pipeline principal de integração TracOS ↔ Cliente.

Este módulo orquestra o fluxo completo de sincronização bidirecional
entre os sistemas Cliente e TracOS, com tratamento robusto de erros,
métricas detalhadas e gestão adequada de recursos.
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass
from loguru import logger

from .client_adapter import client_adapter
from .tracos_adapter import tracos_adapter
from .translator import data_translator


@dataclass
class PipelineMetrics:
    """
    Métricas de execução do pipeline de integração.
    
    Registra contadores, tempos e taxas de sucesso para monitoramento
    e análise de performance do sistema de integração.
    """
    # Contadores gerais
    start_time: datetime
    end_time: Optional[datetime] = None
    
    # Fluxo inbound (Cliente → TracOS)
    inbound_files_read: int = 0
    inbound_files_valid: int = 0
    inbound_converted: int = 0
    inbound_saved: int = 0
    inbound_errors: int = 0
    
    # Fluxo outbound (TracOS → Cliente)
    outbound_workorders_read: int = 0
    outbound_converted: int = 0
    outbound_saved: int = 0
    outbound_synced: int = 0
    outbound_errors: int = 0
    
    def get_execution_time(self) -> float:
        """Retorna o tempo total de execução em segundos."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def get_inbound_success_rate(self) -> float:
        """Retorna a taxa de sucesso do fluxo inbound (0.0 a 1.0)."""
        if self.inbound_files_read == 0:
            return 1.0
        return self.inbound_saved / self.inbound_files_read
    
    def get_outbound_success_rate(self) -> float:
        """Retorna a taxa de sucesso do fluxo outbound (0.0 a 1.0)."""
        if self.outbound_workorders_read == 0:
            return 1.0
        return self.outbound_synced / self.outbound_workorders_read


class IntegrationPipeline:
    """
    Orquestrador principal do pipeline de integração TracOS ↔ Cliente.
    
    Esta classe gerencia os fluxos bidirecionais de sincronização,
    coletando métricas detalhadas, tratando erros de forma isolada
    e garantindo a gestão adequada de recursos do sistema.
    """
    
    def __init__(self):
        """Inicializa o pipeline de integração."""
        self.metrics = PipelineMetrics(start_time=datetime.now())
        logger.info("IntegrationPipeline inicializado")
    
    async def _process_single_inbound_file(self, client_data: Dict) -> bool:
        """
        Processa um único arquivo do fluxo inbound com tratamento de erro isolado.
        
        Args:
            client_data: Dados do cliente a serem processados
            
        Returns:
            True se processado com sucesso, False caso contrário
        """
        try:
            # Validação dos dados do cliente
            if not client_adapter.validate_client_data(client_data):
                logger.warning(f"Dados inválidos para order {client_data.get('orderNo', 'N/A')}")
                return False
            
            self.metrics.inbound_files_valid += 1
            
            # Conversão Cliente → TracOS
            tracos_data = data_translator.client_to_tracos(client_data)
            self.metrics.inbound_converted += 1
            
            # Salvamento no MongoDB
            success = await tracos_adapter.upsert_workorder(tracos_data)
            if success:
                self.metrics.inbound_saved += 1
                logger.debug(f"Workorder {tracos_data['number']} processada com sucesso")
                return True
            else:
                logger.error(f"Falha ao salvar workorder {tracos_data['number']}")
                return False
                
        except Exception as e:
            self.metrics.inbound_errors += 1
            logger.error(f"Erro ao processar arquivo inbound: {e}")
            return False
    
    async def run_inbound_flow(self) -> Dict:
        """
        Executa o fluxo inbound (Cliente → TracOS) com tratamento robusto.
        
        Returns:
            Dicionário com estatísticas do processamento inbound
        """
        logger.info("🔄 Iniciando fluxo inbound (Cliente → TracOS)")
        
        try:
            # Leitura de arquivos do cliente
            files_data = client_adapter.read_inbound_files()
            self.metrics.inbound_files_read = len(files_data)
            
            if not files_data:
                logger.info("Nenhum arquivo encontrado para processamento inbound")
                return self._get_inbound_stats()
            
            logger.info(f"Processando {len(files_data)} arquivo(s) do cliente")
            
            # Processamento individual de cada arquivo
            for i, client_data in enumerate(files_data, 1):
                logger.debug(f"Processando arquivo {i}/{len(files_data)}")
                await self._process_single_inbound_file(client_data)
            
            stats = self._get_inbound_stats()
            logger.info(f"✅ Fluxo inbound concluído: {stats['success_rate']:.1%} sucesso")
            return stats
            
        except Exception as e:
            logger.error(f"Erro crítico no fluxo inbound: {e}")
            return self._get_inbound_stats()
    
    async def _process_single_outbound_workorder(self, tracos_data: Dict) -> bool:
        """
        Processa uma única workorder do fluxo outbound com tratamento de erro isolado.
        
        Args:
            tracos_data: Dados TracOS a serem processados
            
        Returns:
            True se processado com sucesso, False caso contrário
        """
        try:
            workorder_number = tracos_data.get('number', 'N/A')
            
            # Conversão TracOS → Cliente
            client_data = data_translator.tracos_to_client(tracos_data)
            self.metrics.outbound_converted += 1
            
            # Escrita do arquivo de saída
            filename = f"workorder_{workorder_number}.json"
            success = client_adapter.write_outbound_file(filename, client_data)
            
            if not success:
                logger.error(f"Falha ao escrever arquivo para workorder {workorder_number}")
                return False
            
            self.metrics.outbound_saved += 1
            
            # Marcação como sincronizada
            sync_success = await tracos_adapter.mark_as_synced(workorder_number)
            if sync_success:
                self.metrics.outbound_synced += 1
                logger.debug(f"Workorder {workorder_number} sincronizada com sucesso")
                return True
            else:
                logger.warning(f"Workorder {workorder_number} salva mas não marcada como sincronizada")
                return False
                
        except Exception as e:
            self.metrics.outbound_errors += 1
            logger.error(f"Erro ao processar workorder outbound {tracos_data.get('number', 'N/A')}: {e}")
            return False
    
    async def run_outbound_flow(self) -> Dict:
        """
        Executa o fluxo outbound (TracOS → Cliente) com tratamento robusto.
        
        Returns:
            Dicionário com estatísticas do processamento outbound
        """
        logger.info("🔄 Iniciando fluxo outbound (TracOS → Cliente)")
        
        try:
            # Leitura de workorders não sincronizadas
            workorders = await tracos_adapter.read_unsynced_workorders()
            self.metrics.outbound_workorders_read = len(workorders)
            
            if not workorders:
                logger.info("Nenhuma workorder não sincronizada encontrada")
                return self._get_outbound_stats()
            
            logger.info(f"Processando {len(workorders)} workorder(s) não sincronizada(s)")
            
            # Processamento individual de cada workorder
            for i, tracos_data in enumerate(workorders, 1):
                logger.debug(f"Processando workorder {i}/{len(workorders)}")
                await self._process_single_outbound_workorder(tracos_data)
            
            stats = self._get_outbound_stats()
            logger.info(f"✅ Fluxo outbound concluído: {stats['success_rate']:.1%} sucesso")
            return stats
            
        except Exception as e:
            logger.error(f"Erro crítico no fluxo outbound: {e}")
            return self._get_outbound_stats()
    
    def _get_inbound_stats(self) -> Dict:
        """Retorna estatísticas do fluxo inbound."""
        return {
            "files_read": self.metrics.inbound_files_read,
            "files_valid": self.metrics.inbound_files_valid,
            "converted": self.metrics.inbound_converted,
            "saved": self.metrics.inbound_saved,
            "errors": self.metrics.inbound_errors,
            "success_rate": self.metrics.get_inbound_success_rate()
        }
    
    def _get_outbound_stats(self) -> Dict:
        """Retorna estatísticas do fluxo outbound."""
        return {
            "workorders_read": self.metrics.outbound_workorders_read,
            "converted": self.metrics.outbound_converted,
            "saved": self.metrics.outbound_saved,
            "synced": self.metrics.outbound_synced,
            "errors": self.metrics.outbound_errors,
            "success_rate": self.metrics.get_outbound_success_rate()
        }
    
    def _log_final_metrics(self, inbound_stats: Dict, outbound_stats: Dict):
        """
        Registra métricas finais estruturadas do pipeline.
        
        Args:
            inbound_stats: Estatísticas do fluxo inbound
            outbound_stats: Estatísticas do fluxo outbound
        """
        execution_time = self.metrics.get_execution_time()
        
        logger.info("📊 === MÉTRICAS FINAIS DO PIPELINE ===")
        logger.info(f"⏱️  Tempo total de execução: {execution_time:.2f} segundos")
        
        # Métricas inbound
        logger.info(f"📥 Fluxo Inbound (Cliente → TracOS):")
        logger.info(f"   • Arquivos lidos: {inbound_stats['files_read']}")
        logger.info(f"   • Arquivos válidos: {inbound_stats['files_valid']}")
        logger.info(f"   • Convertidos: {inbound_stats['converted']}")
        logger.info(f"   • Salvos: {inbound_stats['saved']}")
        logger.info(f"   • Erros: {inbound_stats['errors']}")
        logger.info(f"   • Taxa de sucesso: {inbound_stats['success_rate']:.1%}")
        
        # Métricas outbound
        logger.info(f"📤 Fluxo Outbound (TracOS → Cliente):")
        logger.info(f"   • Workorders lidas: {outbound_stats['workorders_read']}")
        logger.info(f"   • Convertidas: {outbound_stats['converted']}")
        logger.info(f"   • Arquivos salvos: {outbound_stats['saved']}")
        logger.info(f"   • Sincronizadas: {outbound_stats['synced']}")
        logger.info(f"   • Erros: {outbound_stats['errors']}")
        logger.info(f"   • Taxa de sucesso: {outbound_stats['success_rate']:.1%}")
        
        # Status geral
        total_success_rate = (inbound_stats['success_rate'] + outbound_stats['success_rate']) / 2
        logger.info(f"🎯 Taxa de sucesso geral: {total_success_rate:.1%}")
    
    async def execute_full_pipeline(self) -> Dict:
        """
        Executa o pipeline completo de integração com métricas e cleanup.
        
        Returns:
            Dicionário com todas as métricas e resultados da execução
        """
        logger.info("🚀 === INICIANDO PIPELINE DE INTEGRAÇÃO TracOS ↔ Cliente ===")
        
        try:
            # Execução dos fluxos
            inbound_stats = await self.run_inbound_flow()
            outbound_stats = await self.run_outbound_flow()
            
            # Finalização e métricas
            self.metrics.end_time = datetime.now()
            
            # Cleanup de recursos
            await self._cleanup_resources()
            
            # Logging de métricas finais
            self._log_final_metrics(inbound_stats, outbound_stats)
            
            logger.info("🎉 === PIPELINE DE INTEGRAÇÃO CONCLUÍDO COM SUCESSO ===")
            
            return {
                "execution_time": self.metrics.get_execution_time(),
                "inbound": inbound_stats,
                "outbound": outbound_stats,
                "overall_success": True
            }
            
        except Exception as e:
            logger.error(f"💥 Falha crítica no pipeline: {e}")
            await self._cleanup_resources()
            
            return {
                "execution_time": self.metrics.get_execution_time(),
                "error": str(e),
                "overall_success": False
            }
    
    async def _cleanup_resources(self):
        """
        Realiza limpeza de recursos do sistema (conexões, caches, etc.).
        
        Garante que recursos como conexões MongoDB sejam adequadamente
        fechados ao final da execução do pipeline.
        """
        try:
            # Fechar conexão MongoDB se necessário
            await tracos_adapter.close_connection()
            logger.debug("Recursos do sistema limpos com sucesso")
        except Exception as e:
            logger.warning(f"Aviso durante limpeza de recursos: {e}")


# Instância global do pipeline
integration_pipeline = IntegrationPipeline()

# Funções de compatibilidade (mantêm a interface original)
async def inbound_flow():
    """Função de compatibilidade - executa fluxo inbound via pipeline global."""
    await integration_pipeline.run_inbound_flow()

async def outbound_flow():
    """Função de compatibilidade - executa fluxo outbound via pipeline global."""
    await integration_pipeline.run_outbound_flow()

async def main():
    """
    Função principal que executa o pipeline completo de integração.
    
    Esta é a função de entrada do sistema, orquestrando todo o processo
    de sincronização bidirecional entre Cliente e TracOS.
    """
    await integration_pipeline.execute_full_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
