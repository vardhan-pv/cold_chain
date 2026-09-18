# Source Review and Architecture Decisions

All supplied unique documents were read before source files were created. The final hardware PDF was reviewed on all three pages, the older Phase-I PDF on all 32 pages including its diagrams, and the full text and tables of all Word files and the implementation brief were read. Duplicate uploads were compared by SHA-256 and found identical. `source_inventory.json` records the complete file inventory.

The first baseline preceded the source upload. This integrated delivery additionally reads `softwarepart.docx` in full and audits `cold_chain_project.zip`. The uploaded source and three SQLite snapshots are preserved under `archive/`; the running implementation is merged into one application. See `MERGE_GUIDE.md` for preservation and deliberate schema changes. Files on the laptop beyond the uploaded archive were not accessible.

## Precedence

1. User instruction: the Final Hardware Components List is authoritative.
2. `Cold_Chain_Final_Prototype_Component_List_FIXED(2).pdf` defines the required hardware.
3. `Cold_Chain_Complete_Final_Project_Report(2).docx` supplies compatible functional requirements.
4. `Cold_Chain_Report_Final (1)(1).pdf` supplies the older conceptual objectives.
5. The two Item documents, report procedure, and identical pasted implementation briefs provide supporting workflow details only where compatible with the authoritative list.

## Resolved differences

| Topic | Adopted implementation | Reason |
|---|---|---|
| Controller | ESP32-S3 | Replaces Raspberry Pi / Jetson proposal |
| Cooling | TEC1-12706 plus TEC1-12701 or TEC1-12703 | No compressor or refrigerant circuit |
| Sensors | Two DS18B20, SHT31, one ACS712, reed switch, NEO-6M | Matches final list |
| Pressure and vibration | Excluded from schema and features | Excluded from final hardware |
| Switching | Two independent MOSFET channels with interlock | No relay or servo dependence |
| Fan | Unswitched protected 12 V | Both specified switching channels are used by the Peltiers; no fan driver or tachometer is listed |
| Backup current | Unavailable from installed sensors | The only ACS712 measures the primary branch; external meter evidence is required |
| Shared heatsink | Overtemperature inhibits both Peltiers | Backup cannot remove a fault in their common heat-rejection path |
| OLED and three buttons | Not required; optional display adapter / test inputs only | Added in later documents but absent from authoritative BOM |
| Display and alarm | LEDs, buzzer, dashboard | Fits final components list |
| Database | SQLite through SQLAlchemy | Supported by the implementation roadmap; PostgreSQL route documented, not claimed tested |
| Model location | Full XGBoost/RF inference in Python; deterministic local edge safety | Firmware deployment and resource verification of edge ML remain pending |
| ML target | Binary present-condition anomaly | No labelled failure-time data exists for validated time-to-failure forecasting |
| Rerouting | Temperature/capacity/availability filter and Haversine ranking | No real warehouse catalogue or road routing credentials were supplied |
| Local input reset | Explicit serial acknowledgement / new simulation run | No automatic clearing of critical faults |

The report's example percentages, latency promises, research accuracy figures, and thermal targets are not copied into measured results. Bibliographic claims were not independently verified; they remain source-document claims and are not evidence of this prototype's performance.

## Software control boundary

The simulator runs the local controller even when telemetry is buffered. The backend analyses fresh telemetry and records recommendations. The ESP32 adapter owns physical outputs. It acknowledges a cloud request only when it agrees with current local output state; the network task never changes GPIO. A fresh cloud ML score may raise an expiring advisory warning. No API can directly energize real Peltiers. Backend risk is advisory; sensor evidence and local safety rules control escalation.

Telemetry distinguishes actual reported output state from requested output changes. Logical OFF is not proof of a working MOSFET; primary current supplies additional evidence. A software interlock cannot replace physical protection or detect every wiring failure.

Initial room-temperature cooldown has a provisional 600-second allowance. Hot-side overtemperature, invalid critical sensors, overcurrent, and unexpected primary current remain immediate safety conditions. After reaching the demonstration band, the critical chamber limit applies without a new startup allowance. These assumptions must be replaced by measured commissioning settings.

## Upstream implementation references

- [FastAPI lifespan testing](https://fastapi.tiangolo.com/advanced/testing-events/) was used for correct service startup/cleanup in tests.
- [XGBoost model I/O](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html) informed the JSON model artifact format.
- [Espressif ADC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html) documents calibrated millivolt reads; this does not establish that a purchased ACS712 module can connect directly to the ESP32 ADC.
