#pragma once
// Set actual GPIOs only after verifying the purchased ESP32-S3 pinout.
// COMMISSIONED remains false until sensor, MOSFET and thermal acceptance tests pass.
constexpr bool COMMISSIONED=false;
constexpr int PIN_ONEWIRE=-1,PIN_SDA=-1,PIN_SCL=-1,PIN_CURRENT=-1,PIN_REED=-1;
constexpr int PIN_GPS_RX=-1,PIN_GPS_TX=-1,PIN_PRIMARY=-1,PIN_BACKUP=-1;
constexpr int PIN_GREEN=-1,PIN_YELLOW=-1,PIN_RED=-1,PIN_BUZZER=-1;
constexpr bool CURRENT_CALIBRATED=false;
// Measured AT THE ADC after a verified voltage-conditioning interface.
// Do not use the bare ACS712 5 V sensitivity here unless converted to ADC-side units.
constexpr float CURRENT_ZERO_MV=0,CURRENT_MV_PER_AMP=0;
// Record physical probe ROM IDs; never assign chamber/hot-side by enumeration order.
constexpr uint8_t CHAMBER_ROM[8]={0},HEATSINK_ROM[8]={0};
