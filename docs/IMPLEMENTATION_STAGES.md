# Software First Implementation Stages

This order adapts the original hardware-first roadmap to the user's instruction to proceed while components are pending. Report module numbers and the later pasted stage numbers differ; the table maps by functionality rather than assuming they are identical.

| Stage | Delivered work | Exit evidence | What remains |
|---|---|---|---|
| 1 Requirements reconciliation | Uploaded-code merge, original-data archive, source inventory, precedence and architecture decisions | Complete document review | Exact purchased module details |
| 2 Unified telemetry | Schema, sensor health, GPS provenance, boot/sequence identity | Validation tests and exported JSON schema | Actual firmware stream |
| 3 Local simulator | Seeded plant, real schema, 12 fault scenarios and bounded buffering | Scenario and outage tests | Thermal calibration |
| 4 Backend and database | Authenticated ingestion, transactions, durable controller state, expiring command/ACK lifecycle and APIs | Python and real HTTP integration | Cloud/PostgreSQL deployment |
| 5 Features and models | Causal windows, two trained estimators, ensemble and manifest | Held-out simulation metrics | Measured-data training |
| 6 Self-healing | Hysteresis, sensor fault confirmation, interlock, backup recovery and latch | Python/C++ parity and safety tests | Physical output verification |
| 7 Rerouting | Capability/availability/capacity filter and distance ranking | Routing tests | Real facilities and road network |
| 8 Dashboard | Twelve responsive views, charts, alerts, history and validation export | Build and DOM/API checks | Visual browser approval |
| 9 Firmware preparation | Modular sensor, cooling, display, network and control files | Host controller tests | Full ESP32 compile and all device runtime tests |
| 10 Physical evidence workflow | Measurement register, report analyzer and checklists | Simulation rejection and calculation tests | Hardware evidence |

## Demonstration procedure

Start with normal operation, then use a fresh run for each fault experiment. Keep the source-mode indicator visible. A fault injection is a controlled test input, not a predictive-maintenance discovery. Show both actual model outputs and the separate reason for a sensor-driven transition.

For the main acceptance flow, induce primary failure, observe primary OFF and backup activation, then make backup cooling ineffective. Inspect the critical event, selected compatible demo warehouse, and stored history. Do not present the map as a road route or the simulated temperature drop as measured cooling capacity.

## Documentation for each hardware module later

Record its objective, actual component and board revision, verified wiring, firmware configuration, procedure, expected result, observed result, evidence path, problems/fixes and final status. Leave the observed-result field empty until a real test occurs. Link the measurement record to its acquisition time and device/boot identity.

The original report can be updated after physical results exist. This package deliberately provides a separate implementation record so unmeasured values in the report are not replaced by simulation output.
