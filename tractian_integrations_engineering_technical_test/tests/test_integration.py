"""End-to-end integration tests for the TracOS ↔ Client system."""

import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config import Config
from main import main
from tracos_adapter import TracosAdapter
from mongoDB import MongoService


DATE_FIELDS = ['creationDate', 'lastUpdateDate', 'deletedDate']


class IntegrationTestHelper:
    """Helper for integration tests: setup, cleanup, and validation."""
    
    @staticmethod
    async def cleanup_environment():
        """Integration test should not mutate environment; no-op cleanup."""
        return None
    
    @staticmethod
    def read_json_file(file_path: Path) -> dict:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def compare_datetime_fields(inbound_value: str, outbound_value: str, field: str, file_index: int):
        """Compare datetime fields with a 1-second tolerance."""
        inbound_dt = datetime.fromisoformat(inbound_value.replace('Z', '+00:00'))
        outbound_dt = datetime.fromisoformat(outbound_value.replace('Z', '+00:00'))
        if inbound_dt.tzinfo is None:
            inbound_dt = inbound_dt.replace(tzinfo=timezone.utc)
        if outbound_dt.tzinfo is None:
            outbound_dt = outbound_dt.replace(tzinfo=timezone.utc)
        
        diff = abs((inbound_dt - outbound_dt).total_seconds())
        assert diff < 1.0, \
            f"Field {field} has too large time difference in file {file_index}: {inbound_value} != {outbound_value}"


test_helper = IntegrationTestHelper()


def test_complete_pipeline_end_to_end():
    config = Config()
    
    async def _run_test():
        await test_helper.cleanup_environment()
        # Determine inbound inputs; test should not generate them
        inbound_files = sorted(Path(config.DATA_INBOUND_DIR).glob("*.json"))
        assert len(inbound_files) > 0, (
            f"No inbound files found in {config.DATA_INBOUND_DIR}. "
            f"Provide input JSON files to run the end-to-end integration test. Run: `poetry run python setup.py` to generate the files in data/inbound."
        )

        # Ensure DB is up before running the pipeline, mirroring main.py's behavior
        mongo_ok = await MongoService().health_check()
        assert mongo_ok, (
            "MongoDB is not reachable. Start the database (e.g., 'docker compose up -d') "
            "and run the test again."
        )
        
        await main()
        
        await validate_data_integrity(inbound_files, config)
        # Build list of order numbers from inbound to validate only processed items
        inbound_order_nos: list[int] = []
        for inbound_path in inbound_files:
            data = test_helper.read_json_file(inbound_path)
            if (order_no := data.get('orderNo')) is not None:
                inbound_order_nos.append(order_no)
        await validate_sync_status(order_nos=inbound_order_nos)
        
    asyncio.run(_run_test())


async def validate_data_integrity(inbound_files: list[Path], config: Config):
    """Validate that inbound data equals outbound data (idempotence) and perfect field symmetry."""
    business_fields = [
        'orderNo', 'summary', 'isDone', 'isCanceled', 
        'isOnHold', 'isPending', 'isDeleted', 'deletedDate'
    ]
    
    for inbound_path in inbound_files:
        inbound_data = test_helper.read_json_file(inbound_path)
        order_no = inbound_data.get('orderNo')
        assert order_no is not None, f"Inbound file {inbound_path.name} missing 'orderNo'"
        outbound_path = config.DATA_OUTBOUND_DIR / f"workorder_{order_no}.json"
        assert outbound_path.exists(), f"Expected outbound file not found: {outbound_path}"
        outbound_data = test_helper.read_json_file(outbound_path)
        
        # Validate core business fields (always present)
        for field in business_fields:
            inbound_value = inbound_data.get(field)
            outbound_value = outbound_data.get(field)
            
            if field in DATE_FIELDS and inbound_value and outbound_value:
                test_helper.compare_datetime_fields(inbound_value, outbound_value, field, order_no)
            else:
                assert inbound_value == outbound_value, \
                    f"Field {field} differs for workorder {order_no}: {inbound_value} != {outbound_value}"
        
        # Validate that isActive field is never returned (not supported in this implementation)
        outbound_has_isactive = 'isActive' in outbound_data
        assert not outbound_has_isactive, \
            f"Workorder {order_no}: isActive field should not be returned (not supported)"


async def validate_sync_status(order_nos: list[int]):
    """Validate that records corresponding to inbound order_nos were marked as isSynced=true."""
    adapter = TracosAdapter()
    collection = await adapter.get_workorders_collection()
    
    if not order_nos:
        # Nothing to validate; covered by the earlier assertion of having inbound files
        return

    synced_for_inbound = await collection.count_documents({
        "number": {"$in": order_nos},
        "isSynced": True,
    })
    not_synced_for_inbound = await collection.count_documents({
        "number": {"$in": order_nos},
        "isSynced": {"$ne": True},
    })

    assert synced_for_inbound == len(order_nos), (
        f"Expected all inbound workorders to be synchronized: "
        f"{synced_for_inbound}/{len(order_nos)} are synced"
    )
    assert not_synced_for_inbound == 0, (
        f"There are inbound workorders not synchronized: count={not_synced_for_inbound}"
    )
    
    # Connection is managed by MongoService singleton; optional explicit close
    try:
        await MongoService().close()
    except Exception:
        pass
