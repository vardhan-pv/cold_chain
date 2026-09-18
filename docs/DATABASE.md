# Database Design

SQLAlchemy models in `database/models.py` are the source of truth. `database/schema.sql` is generated from those models for SQLite. Numeric sensor values remain in the validated JSON payload so the same versioned contract is retained without inconsistent duplicate field names.

| Table | Responsibility | Relationship |
|---|---|---|
| devices | Identity, mode, hashed device token, last reception, controller snapshot | Primary key `device_id` |
| telemetry | Acquired/received times, raw payload, decision, archive status | Device foreign key; unique device/boot/sequence |
| predictions | Actual estimator results and provenance | Unique telemetry foreign key |
| fault_events | Warning and fault transitions | Device foreign key |
| self_healing_events | All transitions and supporting evidence | Device foreign key |
| warehouses | Position, capability, capacity, availability, source | Primary key `warehouse_id` |
| rerouting_events | Selection, candidates, method and reason | Device foreign key |
| system_health | Sensor validity, GPS and model availability at receipt | Device foreign key |
| control_commands | Boot/sequence bound intent, expiry, acknowledgement and later confirmation | Device and fault foreign keys; cooling interlock constraint |
| archive_imports | Source digest, name, time and original table counts | Primary key source_sha256 |
| archive_records | Original rows preserved as JSON without replay | Source foreign key; unique source/table/key |
| test_results | Operator-supplied measurement evidence | Device foreign key |

SQLite foreign keys and WAL are enabled. A single service lock serializes ingestion and state transitions within one worker. Every accepted live sample commits telemetry, prediction, transitions, route selection, health, and controller state in one transaction.

Simulation and hardware use different immutable device identities, and all readings retain their mode. Demonstration warehouses have source `SIMULATED`; real hardware selection only considers records explicitly marked `VERIFIED` by the operator. The application does not independently verify a facility's operating status.

This integration creates the canonical tables in a new runtime database and imports older SQLite snapshots into separate archive tables. It preserves the old files unchanged. New command/archive tables are additive for a previously created canonical baseline database. It does not implement a production migration framework, multi-worker locking, automated retention, encrypted database storage, a backup scheduler, or fleet-scale performance tuning. Add those before wider deployment. PostgreSQL mappings are prepared but have not been exercised against a running PostgreSQL instance.
