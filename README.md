# TracOS ↔ Client Integration System

## About the Project

This project implements an asynchronous Python service that simulates a bidirectional integration between Tractian's TracOS CMMS and a customer's ERP system. The system synchronizes work orders between the two systems, performing inbound (Client → TracOS) and outbound (TracOS → Client) flows with data translation and validation.

## Architecture

The system was designed with a clear separation of responsibilities to make it easy to add new integrations without changing existing modules:

### Main Modules
- `client_adapter.py` - Read/write operations with the client system (JSON files).
- `tracos_adapter.py` - Read/write operations with the TracOS system (MongoDB).
- `translator.py` - Bidirectional data translation between systems.
- `mongoDB.py` - Shared MongoDB service: connection singleton, health check, and retry helpers for adapters. This module centralizes database concerns so any current or future adapters can reuse a single, well-tested access layer.
- `config.py` - Centralized configuration via environment variables.
- `main.py` - Main orchestrator of the integration pipeline.

### System Characteristics
- Asynchronous: Non-blocking MongoDB operations for better performance.
- Resilient: Robust handling of I/O errors and transient network failures.
- Idempotent: Safe operations for retry using upsert with unique keys.
- Extensible: Modular architecture enables adding new systems easily.

### Technical Highlights Implemented
- Configuration Singleton Pattern: Centralized configuration loaded once per process.
- Resource Management: Smart reuse of MongoDB connections with cleanup.
- Strict Validation: Required fields and types validated with specific error messages.
- Failure Isolation: A problematic file doesn't stop the entire pipeline.

### Design Decisions and Rationale
- Dedicated `mongoDB.py` module:
  - Single place for connection lifecycle, health checks, and retry behavior.
  - Encourages reuse by any adapter that needs MongoDB, reducing duplication and drift.
  - Makes it simple to evolve cross-cutting DB policies (timeouts, retry rules) without touching business modules.
- Object-Oriented modules (adapters, translator):
  - Encapsulation of behavior and state enables easy extension as the application grows.
  - Clear constructor parameters make new capabilities discoverable (e.g., toggling options, injecting collaborators).
  - Improved testability via dependency injection and explicit lifecycles.
  - Future-proofing: when adding new adapters or changing data sources, we can extend classes and pass new parameters rather than rewriting global functions.
- Dependency Injection in `main.py`:
  - Instances are created and wired at the composition root (no module-level singletons).
  - Promotes isolation across runs and prevents import-time side effects.

## How the System Works

### Inbound Flow (Client → TracOS)
1. Read: Processes JSON files from the `data/inbound/` folder (simulating client API responses).
2. Validate: Checks required fields (`orderNo`, `summary`, `creationDate`).
3. Translate: Converts client format to TracOS format (e.g., boolean statuses → enums).
4. Persist: Saves/updates records in MongoDB with `isSynced=false`.

### Outbound Flow (TracOS → Client)
1. Query: Fetches work orders in MongoDB with `isSynced=false`.
2. Translate: Converts TracOS format to the client format.
3. Generate: Creates JSON files in `data/outbound/` (ready to be "sent" to the client).
4. Mark: Updates records in MongoDB with `isSynced=true` and `syncedAt` timestamp.

### Data Normalization
- Dates: Normalized to UTC ISO 8601.
- Status: Mapping between enums (client uses booleans, TracOS uses strings).
- Fields: Translation between different names and structures.

### Status Mapping Business Rules

The system handles all possible client status combinations with the following priority-based mapping:

| Client Status | Client Flags | TracOS Status | TracOS → Client |
|---------------|--------------|---------------|-----------------|
| **Deleted** | `isDeleted: true` | `"deleted"` | `isDeleted: true`, others `false` |
| **Completed** | `isDone: true` | `"completed"` | `isDone: true`, others `false` |
| **Cancelled** | `isCanceled: true` | `"cancelled"` | `isCanceled: true`, others `false` |
| **On Hold** | `isOnHold: true` | `"on_hold"` | `isOnHold: true`, others `false` |
| **In Progress** | All flags `false` | `"in_progress"` | `isActive: true`, others `false` |
| **Pending** | `isPending: true` | `"pending"` | `isPending: true`, others `false` |

**Priority Order**: The system checks flags in the order listed above. The first `true` flag determines the status.

**Special Case**: When all boolean fields are `false`, the system maps to `"in_progress"` since the client system doesn't have an `isActive` field to represent this state explicitly.

## Project Structure

```
tractian_integrations_engineering_technical_test/
├── docker-compose.yml              # MongoDB container
├── pyproject.toml                  # Poetry dependencies
├── setup.py                        # Initialization script with sample data
├── .env                            # Environment variables
├── data/
│   ├── inbound/                    # Input JSON files (Client → TracOS)
│   └── outbound/                   # Output JSON files (TracOS → Client)
├── src/
│   ├── main.py                     # Main script - runs the full pipeline
│   ├── client_adapter.py           # Module for client system operations
│   ├── tracos_adapter.py           # Module for TracOS system operations
│   ├── translator.py               # Module for format translation
│   ├── mongoDB.py                  # Shared MongoDB service (connection, health, retry)
│   └── config.py                   # Centralized configuration
└── tests/
    └── test_integration.py         # End-to-end tests
```

---

## Prerequisites

Make sure you have installed:
- Python 3.11.x
- Docker and Docker Compose
- Poetry for dependency management

## Environment Setup

Clone this repository:
```bash
git clone https://github.com/gabriel-adutra/cmms-and-erp-integration-simulation.git
cd cmms-and-erp-integration-simulation
```

Before running the commands below, navigate to the project directory:
```bash
cd tractian_integrations_engineering_technical_test/
```

### 1. Install Dependencies
```bash
# Install Poetry (if needed)
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install
```

### 2. Start MongoDB
```bash
# Start MongoDB container
docker compose up -d

# Verify the container is running
docker ps
```

### 3. Initialize Sample Data
```bash
# Create sample data (TracOS + Client)
poetry run python setup.py
```

### 4. Run the Pipeline
```bash
# Run the full bidirectional integration
poetry run python src/main.py
```

### 5. Check Results
```bash
# Check files generated by the pipeline
ls data/outbound/
```

Expected: 10 JSON files named like `workorder_{number}.json` (files are overwritten on each run).

## Tests

### Run End-to-End Tests
```bash
# Simple run
poetry run pytest

# Run with detailed logs (recommended)
poetry run pytest -v -s
```

### What the Tests Validate
- Full pipeline: inbound flow → MongoDB → outbound.
- Correct data translation between Client ↔ TracOS formats.
- Integrity: for existing inbound files, output data matches input (idempotence on business fields).
- Pre-conditions: test fails fast if inbound directory is empty or MongoDB is down.
- Sync semantics: validates that only inbound orderNos are marked as `isSynced=true` in Mongo.
- Pipeline cardinality: the pipeline runs regardless of how many work orders exist in `data/inbound/` (processes all found files).

## Troubleshooting

### Common Issues

MongoDB doesn't connect:
```bash
# Check if the container is running
docker ps | grep mongo

# Restart if needed
docker compose down && docker compose up -d
```

Tests failing:
```bash
# Clean environment and start over
docker compose down -v
docker compose up -d
poetry run pytest -v -s
```

Data not showing up:
```bash
# Check if sample data was created
ls data/inbound/
# If empty, run: poetry run python setup.py
```

---

## Configuration

### Environment Variables
The `.env` file contains the required settings:
```bash
MONGO_URI=mongodb://localhost:27017/tractian
MONGO_DATABASE=tractian
MONGO_COLLECTION=workorders
DATA_INBOUND_DIR=./data/inbound  
DATA_OUTBOUND_DIR=./data/outbound
```

### .env behavior and precedence (python-decouple)
- Automatic loading: keys are read automatically from `.env` if present at the project root.
- Precedence: exported environment variables > values from `.env` > code defaults.
- Safe defaults: if there's no export and no `.env`, default values are used:
  - `MONGO_URI = mongodb://localhost:27017`
  - `MONGO_DATABASE=tractian`
  - `MONGO_COLLECTION=workorders`
  - `DATA_INBOUND_DIR = ./data/inbound`
  - `DATA_OUTBOUND_DIR = ./data/outbound`
- Note: empty values still count as a value. Avoid accidentally setting `MONGO_URI=""`.

## Architecture and Implementation Checklist
These are the technical characteristics implemented in this repository.
- Async I/O with Motor for non-blocking operations.
- Health check on startup and safe MongoDB client shutdown in `finally`.
- Simple retry (3 attempts, 1s) for transient MongoDB errors.
- Idempotency via upsert with unique key (work order number).
- No module-level singletons: dependencies are instantiated and injected in `main`.
- Structured logs (INFO/DEBUG/WARNING/ERROR) with Loguru.
- Modular architecture: adapters, translator, and reusable DB service (`mongoDB.py`).
- Single end-to-end test covering the full pipeline and preconditions (inbound and DB).

### Logging Policy
- INFO: processing milestones (pipeline start/end, totals processed, configuration success).
- DEBUG: details and payloads (e.g., full record contents), useful for local investigation.
- WARNING: recoverable anomalous situations (e.g., invalid file ignored).
- ERROR: non-recoverable failures for the current step (e.g., error after all retry attempts).
Recommendation: use INFO for day-to-day; enable DEBUG only for diagnostics.


### Compliance with project_requirements.md
This section tracks the project's status against the official requirements document (`project_requirements.md`).
- Inbound (read, validate, translate, upsert to Mongo): PASS
- Outbound (fetch `isSynced=false`, translate, write, mark `isSynced=true` + `syncedAt`): PASS
- Normalization (UTC ISO 8601 dates; enums/status): PASS
- Resilience (clear logs, robust I/O, simple retry for Mongo): PASS
- Config via environment variables (with optional `.env`): PASS
- Complete README (structure, how to run, architecture): PASS
- Automated end-to-end test with pytest: PASS


## Data Examples

### Inbound Work Order - Client input:
```json
{
  "orderNo": 1,
  "isCanceled": true,
  "isDeleted": false,
  "isDone": false,
  "isOnHold": false,
  "isPending": false,
  "summary": "Example workorder #1",
  "creationDate": "2025-09-30T23:04:29.045089+00:00",
  "lastUpdateDate": "2025-10-01T00:04:29.045089+00:00",
  "deletedDate": null
}
```

### Work Order in TracOS (Internal MongoDB) after conversion (Client → TracOS):
```json
{
  "_id": "ObjectId('69029d7dbc2225d88a00780d')",
  "number": 1,
  "status": "cancelled",
  "title": "Example workorder #1",
  "description": "Example workorder #1 description",
  "createdAt": "2025-09-30T23:04:29.045Z",
  "updatedAt": "2025-10-29T23:04:29.685Z",
  "deleted": false,
  "isSynced": false
}
```

### Work Order in Outbound after conversion (TracOS → Client):
```json
{
  "orderNo": 1,
  "summary": "Example workorder #1",
  "creationDate": "2025-09-30T23:04:29.045000+00:00",
  "lastUpdateDate": "2025-10-29T23:04:29.685000+00:00",
  "isDeleted": false,
  "deletedDate": null,
  "isDone": false,
  "isCanceled": true,
  "isOnHold": false,
  "isPending": false,
  "isActive": false
}
```

Note: MongoDB stores datetimes with millisecond precision; microseconds may be truncated (e.g., 374263 → 374000).

### Work Order in TracOS (Internal MongoDB) after synchronization:
```json
{
  "_id": "ObjectId('69029d7dbc2225d88a00780d')",
  "number": 1,
  "status": "cancelled", 
  "title": "Example workorder #1",
  "description": "Example workorder #1 description",
  "createdAt": "2025-09-30T23:04:29.045Z",
  "updatedAt": "2025-10-29T23:04:29.685Z",
  "deleted": false,
  "isSynced": true,
  "syncedAt": "2025-10-29T23:04:29.788Z"
}
```

---

*TracOS ↔ Client integration system implemented with a focus on modularity, resilience, and ease of extension to new systems.*