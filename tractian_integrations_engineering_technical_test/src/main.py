""" Main pipeline for CMMS ↔ Client integration.
This module orchestrates the end-to-end bidirectional synchronization between Client and CMMS systems.
"""

import asyncio
from loguru import logger
from client_adapter import ClientAdapter  
from cmms_adapter import CMMSAdapter
from mongoDB import MongoService
from translator import DataTranslator


async def inbound_flow(client_adapter: ClientAdapter, cmms_adapter: CMMSAdapter, translator: DataTranslator):
    """Inbound flow: Client → CMMS. Reads client JSON files, converts to CMMS format, and saves to MongoDB."""

    logger.info("----------------- Starting inbound flow (Client → CMMS) -----------------")
    
    files_data = client_adapter.read_inbound_files()
    if not files_data:
        return None
    
    logger.debug(f"Processing {len(files_data)} workorder(s) found.")
    for client_data in files_data:
        try:
            if not client_adapter.validate_client_data(client_data):
                logger.warning(f"Invalid data: {client_data.get('orderNo', 'N/A')}")
                continue
                
            cmms_data = translator.convert_client_to_cmms(client_data)
            
            await cmms_adapter.upsert_workorder(cmms_data)
            
        except Exception as e:
            logger.error(f"Error during processing: {e}")


async def outbound_flow(client_adapter: ClientAdapter, cmms_adapter: CMMSAdapter, translator: DataTranslator):
    """Outbound flow: CMMS → Client. Reads unsynced workorders from MongoDB, converts to Client format, and generates JSON files."""

    logger.info("----------------- Starting outbound flow (CMMS → Client) -----------------")
    
    workorders = await cmms_adapter.read_unsynced_workorders()
    if not workorders:
        return None
    
    logger.debug(f"Processing {len(workorders)} workorder(s) found.")

    for cmms_data in workorders:
        try:
            client_data = translator.convert_cmms_to_client(cmms_data)

            workorder_number = cmms_data['number']
            filename = f"workorder_{workorder_number}.json"
            success = client_adapter.write_outbound_file(filename, client_data)
            if success:
                await cmms_adapter.mark_workorder_as_synced(workorder_number)
                
        except Exception as e:
            logger.error(f"Error during processing: {e}")


async def main():
    mongo = None  # defensive: ensure name exists for finally block

    try:
        logger.info("=============== STARTING INTEGRATION PIPELINE ===============")

        mongo = MongoService()
        is_ok = await mongo.health_check()
        if not is_ok:
            logger.error("Aborting pipeline: MongoDB is not reachable. Start the database and try again.")
            return

        client_adapter = ClientAdapter()
        cmms_adapter = CMMSAdapter()
        translator = DataTranslator()

        await inbound_flow(client_adapter, cmms_adapter, translator)
        await outbound_flow(client_adapter, cmms_adapter, translator)

        logger.info("=============== PIPELINE COMPLETED SUCCESSFULLY ===============")

    except Exception as e:
        logger.error(f"Critical failure running the integration pipeline: {e}", exc_info=True)
        raise
    
    finally:
        # Always attempt to close the Mongo client; never mask the original error
        if mongo is not None:
            try:
                await mongo.close()
            except Exception:
                logger.warning("Failed to close Mongo client", exc_info=True)



if __name__ == "__main__":
    asyncio.run(main())
