# Software completion record

This delivery merges the user's uploaded project and the earlier software baseline into one runnable application. It completes the local software demonstration pipeline while physical components are pending.

| Stage | Delivered implementation | Verification |
|---|---|---|
| Source reconciliation | Full report review, original source audit, final BOM precedence | Source inventory and merge guide |
| Existing-data preservation | Three byte-preserved SQLite snapshots, 188 lossless archive rows | Hash, row-by-row and repeat-import tests |
| Telemetry and persistence | Validated shared schema, device credentials, boot/sequence deduplication, archived retries | Python tests and real HTTP |
| Fault and control loop | Persistent incidents, expiring commands, scoped polling, idempotent ACK, later confirmation | Recovery, expiry, reboot and cross-device tests |
| Local control | Hysteresis, fault confirmation, primary-OFF evidence, dead time, backup recovery and critical latch | Python/C++ host parity |
| Rerouting | Original fictional warehouse catalogue, compatibility/capacity filters, Haversine ranking, one record per incident | Moving-GPS and no-fix recovery tests |
| Dataset and ML | 10,800 simulated rows, causal features, actual XGBoost/RF, validation-selected ensemble, saved artifacts | Held-out episodes and inference tests |
| Future measured training | Validated labelled JSONL, chronological boot holdouts, evidence hashes, same training/inference features | Software fixtures; no measured model supplied |
| Dashboard | 12 views, real API polling, charts, fault and command history, schematic map, archive browser and exports | JavaScript build and live-API DOM tests |
| Firmware software | ESP32-S3 sensor, local controller, output interlock, telemetry queue, ACK and advisory adapters | Portable controller verified; target build blocked by dependency downloads |
| Validation tools | Physical measurement register, evidence import, JSON/CSV reports and hardware-run analyzer | Calculation and provenance checks |
| Setup and delivery | Windows setup/start scripts, direct Python launcher, API/schema docs, preserved source and evidence | Linux application exercised; Windows instructions not run here |

## Acceptance demonstration

1. Run `START_WINDOWS.bat` after setup. Open the local dashboard.
2. Click **New run** with normal operation. Read the four sensor cards, thermal graph, live model probabilities and sensor-health fields.
3. Apply **Primary cooling failure**. Observe WARNING → PRIMARY_FAULT → BACKUP_ACTIVE → RECOVERY. The Self-healing view shows intent, acknowledgement and subsequent confirmation separately.
4. Start a fresh run with **Primary + backup failure**. Observe primary failure, backup attempt, critical failure and one recommendation to an eligible simulated facility.
5. Select Wi-Fi loss, allow samples to queue, then select normal operation. The local controller continues; buffered samples return as archived records.
6. Review historical original data in **Original project records**, including your existing critical fault and reroute. Export the complete table.
7. Export new telemetry from **Event history** and the still-pending physical measurement register from **Testing & validation**.

Use the machine-readable files in `docs/evidence/` for exact test results. All delivered trained-model performance is based on simulation. Real coolant performance, GPS/sensor operation, electrical switching, measured ML accuracy and physical failure/recovery times remain PENDING_HARDWARE. Full ESP32 target compilation and real-browser visual/mobile verification remain unverified in this environment. Public cloud deployment and a real warehouse service have not been provisioned.
