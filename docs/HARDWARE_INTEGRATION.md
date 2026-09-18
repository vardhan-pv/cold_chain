# Hardware Integration and Wiring Checklist

Every physical step is currently **PENDING_HARDWARE**. The firmware is a prepared adapter, not production-ready or physically verified. Keep `COMMISSIONED=false` throughout sensor bring-up and do not connect Peltier power during initial software tests.

## Before board configuration

1. Record the exact ESP32-S3 board, both sides of its pin labels, flash/PSRAM variant and manufacturer pinout.
2. Record the ACS712 module, MOSFET module, Peltier variant and supply specifications.
3. Confirm actual continuous MOSFET current capacity and 3.3 V input compatibility.
4. Confirm how the primary and backup Peltiers share the cold plate and heatsink; the final BOM provides only one thermal assembly.
5. Match each branch fuse to the actual selected Peltier and wiring. The document's approximate backup fuse is not automatically suitable for every TEC1-12703.

## Wiring checks

- Student signal wiring stays on the low-voltage side. Mains terminals must be enclosed and handled by a competent person.
- Peltier current uses fused suitable power wiring and terminals, never breadboards or thin jumpers.
- The heatsink and continuously powered fan must be installed before either Peltier is energized.
- Verify common signal reference and isolation requirements for the exact MOSFET/sensor modules.
- The ACS712 ADC interface must prevent excessive voltage physically, including fault conditions; no software check replaces this.
- Verify DS18B20 pull-up, non-parasite power, cable condition and actual ROM assignment.
- Verify I2C pull-up voltage and SHT31 address; protect the sensor from condensation.
- Verify GPS supply/logic levels and perform first fix acquisition with a clear sky view.
- Verify LED resistors and buzzer current/voltage drive requirements; a 5 V buzzer is not assumed to be directly drivable by GPIO.
- Confirm gate pull-downs and boot/reset output polarity with the Peltier branches disconnected.
- Inspect insulation, gasket, hot-side airflow, strain relief and separation of power/signal wiring.

## Bring-up order

1. Build the target firmware for the actual board and upload with cooling disabled.
2. Test both temperature probes, SHT31, reed switch and GPS individually. Log invalid/no-fix states as well as valid readings.
3. Calibrate current against a reference meter through the verified ADC interface.
4. Check each output with an appropriate low-power test setup, confirming boot/reset OFF and mutual exclusion.
5. Characterize the assembled primary cooling plant under supervision. Record ambient conditions, temperature trend, hot-side temperature and current.
6. Verify primary OFF and a break-before-make interval before enabling backup. Check real conduction, not only a displayed boolean.
7. Verify shared-heatsink overtemperature disables both Peltiers. The backup must not be treated as a cure for common fan/heatsink failure.
8. Register a separate HARDWARE device, configure private credentials and TLS, and compare serial values to received database records.
9. Test Wi-Fi and backend outages, restart behaviour, queue overflow and watchdog recovery with the physical system.
10. Tune thresholds and thermal observation windows from measured results, then repeat full acceptance tests.

## Records and reporting

Use the measurement register only with real evidence. The `scripts/analyze_hardware_run.py` tool accepts a single hardware device/boot export and produces JSON/CSV. It refuses simulation-labelled input. Mode alone is still a source declaration; an operator must review measurement provenance.

```bat
.venv\Scripts\python.exe scripts\analyze_hardware_run.py runtime\measured_run.json --target 8 --expected-samples 360
```

It calculates available temperature/current/humidity summaries and observed telemetry success from an explicitly supplied generated-sample count. Fault detection timing needs separately observed fault onset; backup current needs an external meter. Unsupported quantities stay pending.

On-device ML deployment, road routing and production cloud operations are separate remaining engineering tasks. Do not energize hardware merely because the desktop simulation succeeds.
