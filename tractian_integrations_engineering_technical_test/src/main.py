""" Main pipeline for TracOS ↔ Client integration.
This module orchestrates the end-to-end bidirectional synchronization between Client and TracOS systems.
"""

import asyncio
from loguru import logger
from client_adapter import ClientAdapter  
from tracos_adapter import TracosAdapter
from mongoDB import MongoService
from translator import DataTranslator


async def inbound_flow(client_adapter: ClientAdapter, tracos_adapter: TracosAdapter, translator: DataTranslator):
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
                
            tracos_data = translator.convert_client_to_tracos(client_data)
            
            await tracos_adapter.upsert_workorder(tracos_data)
            
        except Exception as e:
            logger.error(f"Error during processing: {e}")


async def outbound_flow(client_adapter: ClientAdapter, tracos_adapter: TracosAdapter, translator: DataTranslator):
    """Outbound flow: TracOS → Client. Reads unsynced workorders from MongoDB, converts to Client format, and generates JSON files."""

    logger.info("----------------- Starting outbound flow (TracOS → Client) -----------------")
    
    workorders = await tracos_adapter.read_unsynced_workorders()
    if not workorders:
        return None
    
    logger.debug(f"Processing {len(workorders)} workorder(s) found.")

    for tracos_data in workorders:
        try:
            client_data = translator.convert_tracos_to_client(tracos_data)

            workorder_number = tracos_data['number']
            filename = f"workorder_{workorder_number}.json"
            success = client_adapter.write_outbound_file(filename, client_data)
            if success:
                await tracos_adapter.mark_workorder_as_synced(workorder_number)
                
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
        tracos_adapter = TracosAdapter()
        translator = DataTranslator()

        await inbound_flow(client_adapter, tracos_adapter, translator)
        await outbound_flow(client_adapter, tracos_adapter, translator)

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
