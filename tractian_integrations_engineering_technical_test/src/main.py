""" Pipeline principal de integração TracOS ↔ Cliente. """

import asyncio
from loguru import logger

from client_adapter import read_inbound_files, write_outbound_file, validate_client_data
from tracos_adapter import read_unsynced_workorders, upsert_workorder, mark_as_synced
from translator import client_to_tracos, tracos_to_client


async def inbound_flow():
    """Fluxo Cliente → TracOS."""
    logger.info("Iniciando fluxo inbound (Cliente → TracOS)")
    
    files_data = read_inbound_files()
    processed = 0
    
    for client_data in files_data:
        if validate_client_data(client_data):
            tracos_data = client_to_tracos(client_data)
            success = await upsert_workorder(tracos_data)
            if success:
                processed += 1
    
    logger.info(f"Fluxo inbound finalizado: {processed} workorders processadas")


async def outbound_flow():
    """Fluxo TracOS → Cliente."""
    logger.info("Iniciando fluxo outbound (TracOS → Cliente)")
    
    workorders = await read_unsynced_workorders()
    processed = 0
    
    for tracos_data in workorders:
        client_data = tracos_to_client(tracos_data)
        filename = f"workorder_{tracos_data['number']}.json"
        write_outbound_file(filename, client_data)
        
        success = await mark_as_synced(tracos_data['number'])
        if success:
            processed += 1
    
    logger.info(f"Fluxo outbound finalizado: {processed} workorders sincronizadas")


async def main():
    """Pipeline completo de integração."""
    logger.info("=== Iniciando Pipeline de Integração TracOS ↔ Cliente ===")
    
    await inbound_flow()
    await outbound_flow()
    
    logger.info("=== Pipeline de Integração Finalizado ===")


if __name__ == "__main__":
    asyncio.run(main())
