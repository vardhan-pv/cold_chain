# Firmware Pin Mapping and Configuration

**PENDING_HARDWARE:** the exact purchased ESP32-S3 board model, flash/PSRAM variant and pinout were not supplied. All GPIOs default to `-1`; cooling is disabled. The included PlatformIO board is a generic compile profile, not a verified assignment for the user's board.

Copy `firmware/esp32_s3/commissioning.example.h` to `commissioning.h`. Record the actual verified values in that private local file. Do not reuse the ESP32 DevKit V1 pins from the separate IREOS project.

| Configuration name | Connection | Status |
|---|---|---|
| PIN_ONEWIRE | Both DS18B20 data leads, shared bus | PENDING_HARDWARE |
| CHAMBER_ROM | Eight-byte ID of the chamber probe | PENDING_HARDWARE |
| HEATSINK_ROM | Eight-byte ID of the hot-side probe | PENDING_HARDWARE |
| PIN_SDA / PIN_SCL | SHT31 I2C data/clock | PENDING_HARDWARE |
| PIN_CURRENT | Conditioned ACS712 output, suitable ADC input | PENDING_HARDWARE |
| PIN_REED | Reed contact with defined pull-up/polarity | PENDING_HARDWARE |
| PIN_GPS_RX / PIN_GPS_TX | GPS UART receive/transmit | PENDING_HARDWARE |
| PIN_PRIMARY / PIN_BACKUP | MOSFET logic inputs | PENDING_HARDWARE |
| PIN_GREEN / PIN_YELLOW / PIN_RED | LEDs through resistors, according to fitted count | PENDING_HARDWARE |
| PIN_BUZZER | Appropriate buzzer drive interface | PENDING_HARDWARE |

Select pins compatible with the exact board, avoiding flash/PSRAM, boot straps, USB and other reserved functions. Confirm output polarity. The default assumes active-high logic. Duplicate configured pins and identical probe IDs inhibit commissioning, but this is not a complete board capability validator.

## Current calibration

ACS712 modules commonly use a 5 V supply. **The ADC input must have a verified safe conditioning interface before connection.** Software voltage checks cannot protect a pin from electrical overvoltage. Neither a divider ratio nor sensor sensitivity is assumed for an unseen module.

With `COMMISSIONED=false`, configure the safe ADC input. The serial command `ADC` prints its millivolt reading. Record zero-load ADC voltage and known-load/reference-current pairs. Set `CURRENT_ZERO_MV` and `CURRENT_MV_PER_AMP` in ADC-side units and enable `CURRENT_CALIBRATED` only after verifying the conversion. Mean offset, noise, gain error, response time and the usable range must be documented.

## Sensor assignment and local commands

At startup the firmware prints detected DS18B20 ROM IDs. Physically identify each probe and enter its exact ID; enumeration order is not used. The disconnected and startup sentinel readings are invalidated. A real 85 °C reading is also conservatively invalidated by this prototype adapter and therefore inhibits cooling.

Serial fault controls are explicitly labelled test inputs: `INJECT PRIMARY`, `INJECT BACKUP`, `CLEAR INJECTION`. `RESET CONFIRMED` clears a persistent latch only with configured, valid sensors, cool-enough hot side, low primary current, safe chamber temperature and outputs OFF. It is an operator acknowledgement, not proof that the hardware fault has been repaired.

The base BOM has no OLED, no three-button panel, no fan-speed driver, no fan tachometer and no backup-current sensor. Optional display and injection input code must remain disabled unless those additions are deliberately approved and physically tested.
