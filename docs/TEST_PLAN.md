# Test Plan and Evidence

The delivered evidence separates executable software tests from target-board and physical verification. No photograph, cooldown curve, current calibration, or hardware measurement is fabricated.

## Automated software tests

`python -m pytest -q` covers schema boundaries, authentication, device isolation, idempotency, stale/buffered ingestion, persisted fault latches, real model inference, causal features, split separation, facility filtering and measurement integrity. It also covers the twelve simulator scenarios: normal, primary failure, temperature rise, overcurrent, heatsink overheating, door left open, critical sensor failure, Wi-Fi loss, backend loss, backup failure, no GPS, and recovery.

`python tests/run_live_integration.py` starts Uvicorn on a loopback socket, submits 960 telemetry records across 12 scenarios through actual HTTP, checks persistence and model inference, and verifies primary failure through backup activation and critical rerouting. It stops the server at the end.

With JSDOM installed, set `CC_JSDOM_PATH` to its package path before running that script to also run `tests/dashboard_dom.cjs`. The DOM suite checks all 12 dashboard views, authenticated API rendering, new runs, fault injection, live timeline updates, pause, command status, archive pagination, full history and JSON/CSV export. JSDOM verifies behaviour but does not validate CSS layout or browser rendering.

`node dashboard/build.mjs` checks JavaScript syntax and copies/hashes the four local assets. The application has no runtime CDN dependency.

## Host C++ controller

With `g++` available:

```sh
python tests/firmware/check_parity.py
```

This compiles the actual `control_core.h` on the host, verifies safety assertions and unsigned timer rollover, and replays 2,400 identical sensor records, including variants with and without ML advisory through Python and C++ across the 12 scenarios. Matching state/output results validate the portable rule implementation. They do not exercise GPIO, sensors, networking, NVS, FreeRTOS timing, or the ESP32 toolchain.

## Required physical gates

| Test | Expected evidence | Current status |
|---|---|---|
| Boot, reset, brownout | Both physical output branches inactive | PENDING_HARDWARE |
| DS18B20 and SHT31 | Stable readings and deliberate disconnect behaviour | PENDING_HARDWARE |
| ACS712 | Reference-meter calibration and safe ADC voltage | PENDING_HARDWARE |
| Door/GPS | Debounced door changes, fresh fix/no-fix behaviour | PENDING_HARDWARE |
| Primary cooling | Measured cooldown and steady-state curve | PENDING_HARDWARE |
| Interlock | Oscilloscope/meter observation of no overlapping branch energization | PENDING_HARDWARE |
| Backup recovery | Measured temperature stabilization after primary failure | PENDING_HARDWARE |
| Shared thermal failure | Both channels inhibited; alarm active | PENDING_HARDWARE |
| Communication failure | Local control independent of backend; bounded queue recovery | PENDING_HARDWARE |
| Restart/watchdog | Defined persistent latch and inactive outputs | PENDING_HARDWARE |
| Measured ML | Labelled measured runs and independent held-out evaluation | PENDING_HARDWARE |

Use `docs/evidence/python-tests.xml`, `firmware-parity.json`, `live-integration.json`, and `dashboard-dom.json` as machine-readable software evidence. A passing suite does not imply pharmaceutical compliance or physical reliability.

## Clean-copy launcher check

`python tests/run_launcher_smoke.py` copies the deliverable into a temporary folder, launches `run.py`, registers the standalone simulator, invokes the original `simulator/simulator.py --scenario primary_fault` entry point, verifies stored readings and archive availability, and terminates the server. Credentials and runtime data stay inside that temporary copy.
