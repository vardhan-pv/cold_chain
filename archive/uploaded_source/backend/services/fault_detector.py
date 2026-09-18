"""
Cold-Chain Rule-Based Fault Detection Engine

This module analyzes validated telemetry and determines the
physical operating condition of the cold-chain prototype.

IMPORTANT:
The detector does NOT use the simulator's "scenario" field
to decide whether a fault exists.

The same detector can therefore operate later with real
ESP32-S3 telemetry.

BACKUP_ACTIVE is an operational recovery state, not a new fault.
"""

from dataclasses import dataclass
from typing import Optional


# ============================================================
# SYSTEM STATE CONSTANTS
# ============================================================

STATE_NORMAL = "NORMAL"
STATE_WARNING = "WARNING"
STATE_PRIMARY_FAULT = "PRIMARY_FAULT"
STATE_BACKUP_ACTIVE = "BACKUP_ACTIVE"
STATE_CRITICAL_FAILURE = "CRITICAL_FAILURE"


# ============================================================
# INITIAL PROTOTYPE THRESHOLDS
# ============================================================
#
# Development thresholds only.
# Calibrate later using physical cold-box measurements.
# ============================================================

CHAMBER_WARNING_TEMP_C = 8.0
CHAMBER_CRITICAL_TEMP_C = 12.0

HEATSINK_WARNING_TEMP_C = 55.0
HEATSINK_CRITICAL_TEMP_C = 70.0

PRIMARY_MIN_CURRENT_A = 1.0

HUMIDITY_WARNING_PCT = 90.0


# ============================================================
# DETECTION RESULT
# ============================================================

@dataclass
class FaultDetectionResult:

    fault_detected: bool

    fault_type: Optional[str]

    severity: str

    system_state: str

    description: str


# ============================================================
# MAIN DETECTOR
# ============================================================

def detect_fault(data) -> FaultDetectionResult:
    """
    Analyze one telemetry packet using measured operating data.

    Priority:

    1. Critical thermal conditions
    2. Primary electrical failure
    3. Cooling unavailable
    4. Confirmed backup operation
    5. Non-critical warnings
    6. Normal operation
    """

    # --------------------------------------------------------
    # 1. CRITICAL CHAMBER TEMPERATURE
    # --------------------------------------------------------

    if data.chamber_temp_c >= CHAMBER_CRITICAL_TEMP_C:

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="CHAMBER_TEMPERATURE_CRITICAL",
            severity="CRITICAL",
            system_state=STATE_CRITICAL_FAILURE,
            description=(
                f"Chamber temperature reached "
                f"{data.chamber_temp_c:.2f} C, "
                f"above the critical threshold of "
                f"{CHAMBER_CRITICAL_TEMP_C:.2f} C."
            )
        )

    # --------------------------------------------------------
    # 2. CRITICAL HEATSINK TEMPERATURE
    # --------------------------------------------------------

    if data.heatsink_temp_c >= HEATSINK_CRITICAL_TEMP_C:

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="HEATSINK_OVERHEAT_CRITICAL",
            severity="CRITICAL",
            system_state=STATE_CRITICAL_FAILURE,
            description=(
                f"Heatsink temperature reached "
                f"{data.heatsink_temp_c:.2f} C."
            )
        )

    # --------------------------------------------------------
    # 3. PRIMARY COOLING ELECTRICAL FAILURE
    # --------------------------------------------------------

    if (
        data.primary_cooling
        and data.current_a < PRIMARY_MIN_CURRENT_A
    ):

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="PRIMARY_COOLING_CURRENT_FAILURE",
            severity="HIGH",
            system_state=STATE_PRIMARY_FAULT,
            description=(
                "Primary cooling is commanded ON but "
                f"measured current is only "
                f"{data.current_a:.2f} A."
            )
        )

    # --------------------------------------------------------
    # 4. BOTH COOLING SYSTEMS UNAVAILABLE
    # --------------------------------------------------------

    if (
        data.chamber_temp_c >= CHAMBER_WARNING_TEMP_C
        and not data.primary_cooling
        and not data.backup_cooling
    ):

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="COOLING_UNAVAILABLE",
            severity="HIGH",
            system_state=STATE_PRIMARY_FAULT,
            description=(
                "Chamber temperature is elevated while "
                "both cooling systems are OFF."
            )
        )

    # --------------------------------------------------------
    # 5. BACKUP COOLING CONFIRMED ACTIVE
    # --------------------------------------------------------
    #
    # Critical conditions were checked first.
    #
    # Therefore a moderately elevated chamber temperature does
    # not hide successful backup activation.
    #
    # BACKUP_ACTIVE is deliberately represented with
    # fault_detected=False because it is an operational state,
    # not a new physical fault.
    # --------------------------------------------------------

    if (
        data.backup_cooling
        and not data.primary_cooling
    ):

        return FaultDetectionResult(
            fault_detected=False,
            fault_type=None,
            severity="NONE",
            system_state=STATE_BACKUP_ACTIVE,
            description=(
                "Backup cooling is active and primary "
                "cooling is OFF."
            )
        )

    # --------------------------------------------------------
    # 6. CHAMBER TEMPERATURE WARNING
    # --------------------------------------------------------

    if data.chamber_temp_c >= CHAMBER_WARNING_TEMP_C:

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="CHAMBER_TEMPERATURE_WARNING",
            severity="MEDIUM",
            system_state=STATE_WARNING,
            description=(
                f"Chamber temperature is "
                f"{data.chamber_temp_c:.2f} C."
            )
        )

    # --------------------------------------------------------
    # 7. HEATSINK TEMPERATURE WARNING
    # --------------------------------------------------------

    if data.heatsink_temp_c >= HEATSINK_WARNING_TEMP_C:

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="HEATSINK_TEMPERATURE_WARNING",
            severity="MEDIUM",
            system_state=STATE_WARNING,
            description=(
                f"Heatsink temperature is "
                f"{data.heatsink_temp_c:.2f} C."
            )
        )

    # --------------------------------------------------------
    # 8. DOOR OPEN
    # --------------------------------------------------------

    if data.door_open:

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="DOOR_OPEN",
            severity="LOW",
            system_state=STATE_WARNING,
            description=(
                "Cold-chain chamber door is open."
            )
        )

    # --------------------------------------------------------
    # 9. HIGH HUMIDITY
    # --------------------------------------------------------

    if data.humidity_pct >= HUMIDITY_WARNING_PCT:

        return FaultDetectionResult(
            fault_detected=True,
            fault_type="HIGH_HUMIDITY",
            severity="LOW",
            system_state=STATE_WARNING,
            description=(
                f"Humidity reached "
                f"{data.humidity_pct:.2f}%."
            )
        )

    # --------------------------------------------------------
    # NORMAL
    # --------------------------------------------------------

    return FaultDetectionResult(
        fault_detected=False,
        fault_type=None,
        severity="NONE",
        system_state=STATE_NORMAL,
        description=(
            "Cold-chain system operating normally."
        )
    )