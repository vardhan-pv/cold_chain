# Merge guide: your project plus the completed software stages

`softwarepart.docx` was read in full before this merge. The uploaded source was inspected, including the telemetry, SQLite, fault lifecycle, control command, simulator and rerouting modules. The Final Hardware Components List remains authoritative. The original progress report describes the state before this delivery.

## What was preserved

- `archive/uploaded_source/` contains the uploaded Python source unchanged, for comparison. It is not imported by the running application.
- `archive/databases/cold_chain.db` contains your 103 simulated readings, 6 faults, 1 current-state record, 2 commands and 1 rerouting recommendation.
- The two older database snapshots retain their 16 and 59 telemetry rows.
- `archive/manifest.json` records snapshot hashes and table counts. The 188 total historical rows are imported losslessly into separate archive tables on first startup. Imports are idempotent and never replay past control commands.
- **Original project records** in the dashboard provides all three snapshots, table selection, pagination and complete JSON exports. Historical IDs, timestamps and values remain unchanged.
- Your five simulated warehouse entries (Alpha through Epsilon), their coordinates, capacities and availability are retained. Capacity uses kg; the demonstration requirement is 100 kg. This is simulated cargo configuration, not the small physical enclosure's measured capacity. The integrated controller's entire 5–8 °C demonstration band must fit the destination range.

The uploaded Windows virtual environment was omitted from the deliverable. Recreate it with `SETUP_WINDOWS.bat`; environments contain machine-specific paths and are not portable.

## One active implementation

The merged backend uses one validated telemetry schema, one transaction per ingestion, one persistent controller state, and one pair of real ML estimators. The uploaded flat SQLite schema is not opened as the live database. New operation uses `runtime/cold_chain.db`; trying to use an old-schema database directly produces an actionable error before changing it.

| Original module or behavior | Integrated implementation |
|---|---|
| `backend/models/telemetry.py` | `backend/schemas.py` and generated JSON schema |
| `backend/database/db.py` | `database/models.py`, `backend/service.py`, `backend/archive.py` |
| `fault_detector.py` | Python `backend/control.py` and host-tested C++ `control_core.h` |
| `fault_manager.py` | `backend/faults.py`: persistent incidents, mitigation and resolution |
| `self_healing.py` | Controller decisions plus `backend/commands.py` |
| Command pending / ACK API | Authenticated versions at the same `/api/v1/control/...` paths |
| `warehouse_registry.py`, `rerouting.py` | `backend/routing.py`; original catalogue and deduplication by incident |
| `simulator/simulator.py` | Compatible entry point, upgraded simulator engine and HTTP client |
| Empty ML/dashboard/firmware folders | Integrated models, 12-view dashboard and firmware adapter |

## Deliberate changes

`session_id` becomes `boot_id` in the canonical request. `current_a` becomes **primary_current_a**. Legacy packets do not contain sensor validity, SHT31 secondary temperature, uptime or GPS age and cannot be silently treated as equivalent hardware telemetry. The replacement simulator and firmware use the complete contract. Old-format POSTs receive 422; old records remain accessible through the archive. The `/api/v1/telemetry` URL is retained, along with read, control and rerouting routes. Read response bodies now expose canonical fields. Device requests require a device token; dashboard/read requests require the operator token.

The old simulator produced approximately 2 A in `current_a` during backup operation. The authoritative hardware has one ACS712 on the **primary** branch, so new simulation correctly reports primary current near zero when primary cooling is OFF. It never invents a backup-current sensor. Existing historical values are preserved with a warning about their original meaning.

Prototype thresholds are explicit in `backend/control.py` and `firmware/esp32_s3/control_core.h`: hysteresis 5–8 °C, warning above 10 °C, chamber critical 18 °C after initial cooldown, hot-side cutoff 65 °C, primary overcurrent 7 A, primary minimum 0.3 A after a 10-second grace and 10-second confirmation, and a 2-second interlock. These replace the earlier provisional 12/70 °C and immediate low-current rules. A 600-second initial warm-box allowance prevents startup being mistaken for cooling failure. These are development settings requiring physical calibration.

Backup GPIO reporting mitigates the incident; it does not prove equipment repair or measured cooling capacity. Critical failures stay latched. A new simulation run starts a new device identity. For hardware, a local manual reset and safe fresh telemetry must precede operator reconciliation of the backend latch; see `COMMAND_PROTOCOL.md`.

## Running it alongside your existing folder

Extract to a new folder such as `E:\cold_chain_project_complete` first. Keep the original `E:\cold_chain_project` until you have run the delivered version. Close the old server so port 8000 is free. Run `SETUP_WINDOWS.bat` once, then `START_WINDOWS.bat`.

Do not copy the old `.venv` or overwrite the new runtime database with an old-schema file. To import any additional older database:

```bat
.venv\Scripts\python.exe scripts\import_legacy.py "E:\cold_chain_project\database\cold_chain.db"
```

This adds historical archive records without changing the source file or activating its commands. The snapshots already included in this package are imported automatically.
