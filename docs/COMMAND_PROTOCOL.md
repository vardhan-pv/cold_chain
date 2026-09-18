# Command and incident protocol

The backend records desired output states. The simulator or ESP32 local safety loop decides whether those states are permissible. Network availability is never required for the ESP32 to inhibit unsafe cooling.

1. A fresh authenticated telemetry record is validated and saved with its ML inference and controller decision.
2. An output change or state transition creates a boot-bound command. Only one current pending intent is offered. The two outputs cannot both be ON, including at the database constraint.
3. The device polls `GET /api/v1/control/{device_id}/pending` with `X-Device-Token`.
4. The device compares the command against its local safety controller. Agreement can be acknowledged as APPLIED. Disagreement is REJECTED. Firmware polling never writes GPIO.
5. The device posts an acknowledgement body to `/api/v1/control/{command_id}/acknowledge` with the same device token.
6. A later telemetry record, with a sequence strictly greater than both the command evidence and acknowledgement sequence, must show the requested outputs before the status becomes CONFIRMED.

An acknowledgement contains `device_id`, `boot_id`, `sequence`, `outcome` (APPLIED or REJECTED), `primary_cooling`, `backup_cooling`, and a reason. See OpenAPI for the complete schema. The same acknowledgement can be retried idempotently. A different device, boot, old sequence, conflicting output, superseded command or expired command is rejected.

Commands expire after 30 wall-clock seconds. A new boot supersedes old pending commands; controller fault latches are preserved. Buffered and out-of-order telemetry is historical only and cannot create or confirm commands. During a primary fault, STOP_ALL_COOLING and primary-OFF/current evidence precede ACTIVATE_BACKUP_COOLING. A command cannot shorten the local dead time.

Statuses: PENDING → ACKNOWLEDGED → CONFIRMED. Alternate endings: REJECTED, EXPIRED, SUPERSEDED. CONFIRMED refers to subsequent reported output flags. It does not claim physical MOSFET conduction or hardware verification. The primary current sensor and thermal evidence remain separate observations.

The simulator executes the same controller locally and acknowledges agreement with it. Its built-in dashboard version uses the same service methods; the standalone simulator exercises actual HTTP polling and acknowledgement. The supplied live integration test verifies both the stored command lifecycle and subsequent telemetry.

## Fault lifecycle and rerouting

One active incident is maintained for each dominant fault category. Repeated packets do not create duplicate active incidents. Backup observation resolves the primary incident as MITIGATED_BY_BACKUP, with hardware repair explicitly unverified. Critical incidents remain active through REROUTING.

One rerouting record belongs to each critical incident. Changing GPS positions do not produce another recommendation every packet. If GPS or a compatible facility is initially missing, the same record can be completed when data becomes available. A selected recommendation retains the position and facility snapshot used when it was selected; it is not a moving navigation route or a live capacity reservation.

## Manual reset reconciliation

Firmware's local `RESET CONFIRMED` command remains subject to local safe-reset checks. After an operator has actually cleared the local latch, the backend latch is deliberately retained until reconciled:

`POST /api/devices/{device_id}/reconcile-reset`, authenticated with the operator bearer token, with a JSON body containing the current `boot_id` and a descriptive `reason`.

Reconciliation requires fresh, non-archived telemetry, matching boot, local NORMAL/WARNING state, valid critical sensors, chamber below 18 °C, heatsink below 50 °C, current below 7 A, no active injection and no unexplained current when primary is OFF. It records the operator reason and sensor evidence, supersedes old commands, and clears the backend latch. It sends no reset or actuation instruction to hardware. The next sample updates the dashboard decision normally.

## ML at the edge

The full models run on the backend. Firmware may consume a valid ensemble risk from a fresh ingestion response, with a 20-second expiry. It can only raise an advisory warning. Invalid sensors, overcurrent, overtemperature, latches and local interlocks have priority. No on-device XGBoost model or field accuracy is claimed. The added C++ advisory rule is included in host parity tests; ESP32 network/runtime behavior still needs target and hardware validation.
