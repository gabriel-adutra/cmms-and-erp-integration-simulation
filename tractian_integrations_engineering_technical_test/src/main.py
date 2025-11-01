""" Main pipeline for TracOS ↔ Client integration.
This module orchestrates the end-to-end bidirectional synchronization between Client and TracOS systems.
"""

import asyncio
from loguru import logger
from client_adapter import client_adapter  
from tracos_adapter import tracos_adapter
from translator import data_translator



async def inbound_flow():
    """Inbound flow: Client → TracOS. Reads client JSON files, converts to TracOS format, and saves to MongoDB."""

    logger.info("----------------- Starting inbound flow (Client → TracOS) -----------------")
    
    files_data = client_adapter.read_inbound_files()
    if not files_data:
        return None
    
    logger.debug(f"Processing {len(files_data)} workorder(s) found.")
    for client_data in files_data:
        try:
            if not client_adapter.validate_client_data(client_data):
                logger.warning(f"Invalid data: {client_data.get('orderNo', 'N/A')}")
                continue
                
            tracos_data = data_translator.convert_client_to_tracos(client_data)
            
            await tracos_adapter.upsert_workorder(tracos_data)
            
        except Exception as e:
            logger.error(f"Error during processing: {e}")


async def outbound_flow():
    """Outbound flow: TracOS → Client. Reads unsynced workorders from MongoDB, converts to Client format, and generates JSON files."""

    logger.info("----------------- Starting outbound flow (TracOS → Client) -----------------")
    
    workorders = await tracos_adapter.read_unsynced_workorders()
    if not workorders:
        return None
    
    logger.debug(f"Processing {len(workorders)} workorder(s) found.")

    for tracos_data in workorders:
        try:
            client_data = data_translator.convert_tracos_to_client(tracos_data)

            workorder_number = tracos_data['number']
            filename = f"workorder_{workorder_number}.json"
            success = client_adapter.write_outbound_file(filename, client_data)
            if success:
                await tracos_adapter.mark_workorder_as_synced(workorder_number)
                
        except Exception as e:
            logger.error(f"Error during processing: {e}")


async def main():
    
    try:
        logger.info("=============== STARTING INTEGRATION PIPELINE ===============")

        await inbound_flow()
        await outbound_flow()
        await tracos_adapter.close_connection()
        
        logger.info("=============== PIPELINE COMPLETED SUCCESSFULLY ===============")
        
    except Exception as e:
        logger.error(f"Critical failure running the integration pipeline: {e}", exc_info=True)
        await tracos_adapter.close_connection()
        raise



if __name__ == "__main__":
    asyncio.run(main())
