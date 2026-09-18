# ESP32-S3 firmware

The adapter is prepared for the final BOM and disabled by default. It requires the exact board, pin map, DS18B20 ROM identities, ACS712 calibration/ADC conditioning, local supply and output-driver checks before commissioning.

Full target compilation could not run in the delivery environment because the official PlatformIO package mirrors timed out. See `../docs/evidence/firmware-target-build.json`. The portable C++ controller was compiled and tested on the host; this does not substitute for the target build.

On a normally connected development machine, from the project root:

```sh
python -m pip install platformio==6.2.0
python -m platformio run --project-dir firmware
```

The supplied profile is `esp32-s3-devkitc-1` for a generic compile check. Confirm actual flash/PSRAM and board before upload. Default `COMMISSIONED=false` and unassigned pins inhibit the cooling outputs. Do not bypass these settings to make a disconnected demonstration appear operational.

Copy and fill `commissioning.example.h` and `secrets.example.h` only during hardware integration. Real commissioning/secrets files are excluded from packaging and source control. TLS certificate validation stays enabled; isolated-LAN HTTP requires the explicit lab setting. No network task writes GPIO. It may acknowledge agreement with local outputs and deliver a fresh ML advisory; the local controller retains priority.

Use `../docs/HARDWARE_INTEGRATION.md`, `PIN_MAPPING.md` and `COMMAND_PROTOCOL.md` for calibration, physical tests, command acknowledgement and manual-reset reconciliation.
