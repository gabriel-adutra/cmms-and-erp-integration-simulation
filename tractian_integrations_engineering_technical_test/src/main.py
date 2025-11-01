""" Pipeline principal de integração TracOS ↔ Cliente. 
Este módulo orquestra o fluxo completo de sincronização bidirecional entre os sistemas Cliente e TracOS. 
"""

import asyncio
from loguru import logger
from client_adapter import client_adapter  
from tracos_adapter import tracos_adapter
from translator import data_translator



async def inbound_flow():
    """ Fluxo inbound: Cliente → TracOS. Lê arquivos JSON do cliente, converte para formato TracOS e salva no MongoDB."""

    logger.info("----------------- Iniciando fluxo inbound (Cliente → TracOS) -----------------")
    
    files_data = client_adapter.read_inbound_files()
    if not files_data:
        logger.info("Nenhum arquivo encontrado.")
        return None
    
    logger.debug(f"Processando {len(files_data)} workorder(s) encontrados.")
    for client_data in files_data:
        try:
            if not client_adapter.validate_client_data(client_data):
                logger.warning(f"Dados inválidos: {client_data.get('orderNo', 'N/A')}")
                continue
                
            tracos_data = data_translator.convert_client_to_tracos(client_data)
            
            await tracos_adapter.upsert_workorder(tracos_data)
            
        except Exception as e:
            logger.error(f"Erro no processamento: {e}")


async def outbound_flow():
    """ Fluxo outbound: TracOS → Cliente. Lê workorders não sincronizadas do MongoDB, converte para formato Cliente e gera arquivos JSON."""

    logger.info("----------------- Iniciando fluxo outbound (TracOS → Cliente) ----------------- ")
    
    workorders = await tracos_adapter.read_unsynced_workorders()
    if not workorders:
        return None
    
    logger.debug(f"Processando {len(workorders)} workorder(s) encontrados.")

    for tracos_data in workorders:
        try:
            client_data = data_translator.convert_tracos_to_client(tracos_data)
            
            workorder_number = tracos_data['number']
            filename = f"workorder_{workorder_number}.json"
            success = client_adapter.write_outbound_file(filename, client_data)
            if success:
                await tracos_adapter.mark_workorder_as_synced(workorder_number)
                
        except Exception as e:
            logger.error(f"Erro no processamento: {e}")


async def main():
    
    try:
        logger.info("=============== INICIANDO PIPELINE DE INTEGRAÇÃO ===============")

        await inbound_flow()
        await outbound_flow()
        await tracos_adapter.close_connection()
        
        logger.info("=============== PIPELINE CONCLUÍDO COM SUCESSO ===============")
        
    except Exception as e:
        logger.error(f"Falha crítica na execução do pipeline de integração: {e}", exc_info=True)
        await tracos_adapter.close_connection()
        raise



if __name__ == "__main__":
    asyncio.run(main())
