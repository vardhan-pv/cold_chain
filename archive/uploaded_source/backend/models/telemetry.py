"""
Cold-Chain Telemetry Data Models

Defines and validates telemetry received from:
- Python digital simulator
- ESP32-S3 hardware later

The API contract is intentionally shared by both sources.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# GPS MODEL
# ============================================================

class GPSData(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    latitude: float = Field(
        ge=-90,
        le=90
    )

    longitude: float = Field(
        ge=-180,
        le=180
    )

    valid: bool

    source: Literal[
        "SIMULATED",
        "GPS"
    ]


# ============================================================
# TELEMETRY MODEL
# ============================================================

class TelemetryData(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    # --------------------------------------------------------
    # DEVICE / PACKET IDENTITY
    # --------------------------------------------------------

    device_id: str = Field(
        min_length=1,
        max_length=50
    )

    session_id: str = Field(
        min_length=1,
        max_length=100
    )

    sequence: int = Field(
        ge=1
    )

    timestamp: datetime

    # --------------------------------------------------------
    # SOURCE INFORMATION
    # --------------------------------------------------------

    telemetry_source: Literal[
        "SIMULATOR",
        "ESP32"
    ]

    simulation_mode: bool

    # --------------------------------------------------------
    # SENSOR VALUES
    # --------------------------------------------------------

    chamber_temp_c: float = Field(
        ge=-50,
        le=100
    )

    heatsink_temp_c: float = Field(
        ge=-50,
        le=150
    )

    humidity_pct: float = Field(
        ge=0,
        le=100
    )

    current_a: float = Field(
        ge=0,
        le=50
    )

    # --------------------------------------------------------
    # DOOR SENSOR
    # --------------------------------------------------------

    door_open: bool

    # --------------------------------------------------------
    # COOLING STATUS
    # --------------------------------------------------------

    primary_cooling: bool

    backup_cooling: bool

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    gps: GPSData

    # --------------------------------------------------------
    # SIMULATION LABEL
    # --------------------------------------------------------
    #
    # This is for test/evidence purposes.
    #
    # The fault detector MUST NOT use this field to determine
    # whether a fault exists.
    # --------------------------------------------------------

    scenario: str = Field(
        min_length=1,
        max_length=50
    )