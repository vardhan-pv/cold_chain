# Troubleshooting

| Symptom | Check and action |
|---|---|
| `py` not recognized | Install Python 3.12 or use the full path to an installed interpreter. |
| A module is missing | Run the requirements installation with the same `.venv` interpreter used to launch the app. |
| Port 8000 is occupied | Use `python run.py --port 8001` and open that port. |
| Dashboard asks for a token | Copy the operator token from your own local launcher terminal. Do not post it in chat or commit it. |
| 401 on telemetry | Use the device token returned by registration, not the operator token. Confirm the device ID. |
| 409 on registration | That identity already exists. Preserve its credentials or register a new identity; registration does not overwrite it. |
| 409 on telemetry | Check immutable mode and uniqueness of boot ID/sequence; never reuse a sequence with changed data. |
| 422 sensor payload | Use the canonical schema. Invalid sensor values must be null with false health flags. Check timezone and GPS fix age. |
| ML unavailable | Confirm both artifacts and the manifest exist and hashes match. Retrain with the documented environment and restart the service. |
| Predicted risk unavailable | A required sensor is invalid or an artifact failed validation. This is deliberate; no substitute probability is invented. |
| Critical fault remains after choosing normal | Faults are latched. Start a new simulation run; hardware requires an explicit safe manual reset after inspection. |
| Status becomes stale | No fresh sample has arrived in 20 seconds. Check pause, Wi-Fi/backend failure scenario, and the sender. |
| Old samples reappear after reconnection | Buffered samples are archived. They do not become the latest live value or replay actuation. |
| Hardware cannot reach localhost | The ESP32 needs the laptop's LAN address or a deployed HTTPS endpoint. `127.0.0.1` refers to the device itself. |
| No real GPS fix | Coordinates remain null. Do not relabel fictional coordinates as real GPS. |
| No warehouse selected | Check fresh GPS, temperature range, availability, capacity, and SIMULATED versus VERIFIED source. |
| Fan speed or backup-current value is missing | The authoritative BOM includes neither fan control/feedback nor a backup-current sensor. |
| Firmware refuses cooling | Pins, distinct probe IDs, calibration and COMMISSIONED must be verified. Do not bypass these conditions to test an unknown power circuit. |
| ESP32 build dependencies do not download | Retry the documented PlatformIO build on a normally connected development machine. Do not disable checksum verification. |

The default server is local and uses one worker. Cloud deployment, role-based access, notification providers, production monitoring, retention policies, a road-routing service and measured-data ML are not configured by this package.
