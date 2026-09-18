# API Contract

The backend defaults to `http://127.0.0.1:8000`. Complete generated schemas are in `openapi.json` and `telemetry.schema.json`. `/docs` exposes FastAPI's interactive documentation; its default Swagger assets require internet access. The project dashboard itself has no CDN dependency.

All operator endpoints require `Authorization: Bearer <operator-token>`. Ingestion requires `X-Device-Token: <device-token>`, scoped to one registered device. Registration returns that device secret once; the database stores its SHA-256 hash. The operator token comes from the environment or the private local runtime file, never from source code.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Minimal public liveness |
| POST / GET | `/api/devices` | Register or list units |
| POST | `/api/telemetry` | Validate and ingest one sample |
| GET | `/api/latest?device_id=...` | Latest fresh sample, prediction, route, reception age |
| GET | `/api/history?device_id=...&limit=200` | Latest telemetry records, newest first |
| GET | `/api/predictions?device_id=...` | Model inference history |
| GET | `/api/faults?device_id=...` | Warning and failure records |
| GET | `/api/self-healing?device_id=...` | State transition audit trail |
| GET | `/api/rerouting?device_id=...` | Facility-selection results |
| GET / PUT | `/api/warehouses` | Read or upsert a facility |
| GET | `/api/system-status` | Model and simulator availability |
| GET | `/api/system-health?device_id=...` | Recorded sensor/communication status |
| POST | `/api/simulation/start` | Create a distinct simulated run |
| POST | `/api/simulation/scenario` | Change the current simulated fault |
| POST | `/api/simulation/pause` | Pause/resume simulated acquisition |
| GET / POST | `/api/validation` | Measurement register / evidence submission |
| GET | `/api/validation/export?device_id=...&format=csv` | Export measurement register |

The report's `/api/v1/telemetry`, `/api/v1/status/{device_id}`, `/api/v1/history/{device_id}`, `/api/v1/events/{device_id}`, and `/api/v1/predictions/{device_id}` paths are compatibility aliases. Rerouting is automatically invoked for fresh critical telemetry; it is not a real navigation instruction or a warehouse reservation.

## Telemetry rules

The canonical current field is `primary_current_a`. Earlier examples named it `current_a` or `current`; those are not silently accepted. Use the exported JSON schema for both simulator and firmware. Timestamps require a UTC offset. Every sample contains `device_id`, `boot_id`, and `sequence` to make retries idempotent.

Unavailable sensor values are JSON null with matching false health flags. GPS without a fix has null coordinates, null speed, and source `NONE`. A valid fix requires a position no more than 30 seconds old. Hardware identities reject simulated coordinates, and a device's SIMULATION/HARDWARE mode cannot be changed after registration.

Repeated identity/boot/sequence with identical content succeeds with `duplicate=true` and no replayed command. Reusing that identity with different measurements returns 409. Buffered, stale, out-of-order, or retired-boot samples are stored as archived and cannot drive live transitions. A hardware timestamp more than 30 seconds in the future is rejected.

Current state is persisted transactionally with telemetry and related events. An edge-reported fault after reconnection is retained. Backend restart does not clear the last controller latch. Read history is capped at 2,000 rows per request; use `offset` to paginate and `/api/history/export?device_id=...` for a complete JSON download.

Typical errors: 401 incorrect credentials; 404 unknown device; 409 identity/mode/sequence conflict; 422 invalid schema. No endpoint directly controls real GPIO outputs.

## Integrated project additions

| Method | Endpoint | Authentication and purpose |
|---|---|---|
| GET | `/api/v1/control/{device_id}/pending` | Device token; current boot-bound unexpired intent |
| POST | `/api/v1/control/{command_id}/acknowledge` | Device token and acknowledgement body; see COMMAND_PROTOCOL.md |
| GET | `/api/v1/control/{device_id}/history` | Operator; command lifecycle history |
| GET | `/api/commands?device_id=...` | Operator; same canonical command rows |
| GET | `/api/v1/telemetry/{device_id}/latest` or `/history` | Operator; uploaded read routes, canonical response fields |
| GET | `/api/v1/rerouting/{device_id}/latest` or `/history` | Operator; uploaded rerouting routes |
| GET | `/api/archive` | Operator; original snapshot hashes and table counts |
| GET | `/api/archive/{sha256}/{table}?limit=50&offset=0` | Operator; lossless original records, optional device_id filter |
| GET | `/api/history/export?device_id=...` | Operator; full canonical history, streamed JSON |
| POST | `/api/devices/{device_id}/reconcile-reset` | Operator; audited acknowledgement of a safe completed local reset |

Archive table names are restricted to telemetry, fault_events, system_state, control_commands and rerouting_events. Original historical records are not mixed into live control or measurement evidence. The old unauthenticated APIs and body-less command ACK have deliberately been replaced.
