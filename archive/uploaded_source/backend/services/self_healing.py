"""
Cold-Chain Self-Healing Controller
==================================

This service converts confirmed fault states into control commands.

Important architecture:

    Telemetry
        ↓
    Fault Detector
        ↓
    Fault Lifecycle Manager
        ↓
    Self-Healing Controller
        ↓
    control_commands table
        ↓
    Simulator / ESP32-S3
        ↓
    Physical or simulated actuator response

The controller DOES NOT directly modify telemetry.

During software development, the simulator will later fetch and
acknowledge these commands.

During hardware deployment, the ESP32-S3 will perform the same role.
"""

from datetime import datetime, timezone

from backend.database.db import (
    create_control_command,
    get_pending_command_by_type,
)


# ============================================================
# COMMAND TYPES
# ============================================================

COMMAND_ACTIVATE_BACKUP = "ACTIVATE_BACKUP_COOLING"

COMMAND_STOP_ALL_COOLING = "STOP_ALL_COOLING"

COMMAND_RESTORE_PRIMARY = "RESTORE_PRIMARY_COOLING"


# ============================================================
# FAULT TYPES
# ============================================================

FAULT_PRIMARY_CURRENT = "PRIMARY_COOLING_CURRENT_FAILURE"

FAULT_CHAMBER_CRITICAL = "CHAMBER_TEMPERATURE_CRITICAL"

FAULT_HEATSINK_CRITICAL = "HEATSINK_OVERHEAT_CRITICAL"


# ============================================================
# SYSTEM STATES
# ============================================================

STATE_PRIMARY_FAULT = "PRIMARY_FAULT"

STATE_CRITICAL_FAILURE = "CRITICAL_FAILURE"


# ============================================================
# CREATE COMMAND SAFELY
# ============================================================

def _create_command_if_needed(
    device_id,
    session_id,
    command_type,
    primary_cooling,
    backup_cooling,
    reason,
    fault_id,
):
    """
    Create a command only when an identical command is not
    already waiting for the device.

    This prevents a new command from being generated for every
    telemetry packet while the same fault remains active.
    """

    existing = get_pending_command_by_type(
        device_id,
        command_type,
    )

    if existing is not None:

        return {
            "command_created": False,
            "command_id": existing["id"],
            "command_type": existing["command_type"],
            "primary_cooling": bool(
                existing["primary_cooling"]
            ),
            "backup_cooling": bool(
                existing["backup_cooling"]
            ),
            "status": existing["status"],
            "reason": "Equivalent command already pending.",
        }

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    command_id = create_control_command(
        device_id=device_id,
        session_id=session_id,
        command_type=command_type,
        primary_cooling=primary_cooling,
        backup_cooling=backup_cooling,
        reason=reason,
        triggered_by_fault=fault_id,
        created_at=created_at,
    )

    return {
        "command_created": True,
        "command_id": command_id,
        "command_type": command_type,
        "primary_cooling": primary_cooling,
        "backup_cooling": backup_cooling,
        "status": "PENDING",
        "reason": reason,
    }


# ============================================================
# SELF-HEALING DECISION ENGINE
# ============================================================

def evaluate_self_healing(
    data,
    fault_result,
):
    """
    Evaluate whether the current fault requires an automatic
    control action.

    Parameters
    ----------
    data:
        Validated TelemetryData object.

    fault_result:
        Result returned by process_fault_lifecycle().

    Returns
    -------
    Dictionary describing the self-healing decision.
    """

    default_result = {
        "action_required": False,
        "command_created": False,
        "command_id": None,
        "command_type": None,
        "primary_cooling": None,
        "backup_cooling": None,
        "status": None,
        "reason": None,
    }

    if not fault_result:
        return default_result

    if not fault_result.get(
        "fault_detected",
        False,
    ):
        return default_result

    fault_type = fault_result.get(
        "fault_type"
    )

    system_state = fault_result.get(
        "system_state"
    )

    fault_id = fault_result.get(
        "fault_id"
    )

    # ========================================================
    # RULE 1
    # PRIMARY COOLING ELECTRICAL FAILURE
    # ========================================================
    #
    # Primary cooling is commanded ON, but measured current
    # indicates that it is not operating correctly.
    #
    # Recovery:
    #     Primary OFF
    #     Backup ON
    # ========================================================

    if (
        fault_type == FAULT_PRIMARY_CURRENT
        and system_state == STATE_PRIMARY_FAULT
    ):

        result = _create_command_if_needed(
            device_id=data.device_id,
            session_id=data.session_id,

            command_type=COMMAND_ACTIVATE_BACKUP,

            primary_cooling=False,
            backup_cooling=True,

            reason=(
                "Primary cooling current failure detected. "
                "Disable primary cooling and activate "
                "backup cooling."
            ),

            fault_id=fault_id,
        )

        result["action_required"] = True

        return result

    # ========================================================
    # RULE 2
    # CRITICAL HEATSINK OVERHEATING
    # ========================================================
    #
    # For safety, both cooling modules are requested OFF.
    #
    # Later the critical-failure/rerouting service will handle
    # escalation after this command.
    # ========================================================

    if (
        fault_type == FAULT_HEATSINK_CRITICAL
        and system_state == STATE_CRITICAL_FAILURE
    ):

        result = _create_command_if_needed(
            device_id=data.device_id,
            session_id=data.session_id,

            command_type=COMMAND_STOP_ALL_COOLING,

            primary_cooling=False,
            backup_cooling=False,

            reason=(
                "Critical heatsink temperature detected. "
                "Stop cooling outputs for thermal protection."
            ),

            fault_id=fault_id,
        )

        result["action_required"] = True

        return result

    # ========================================================
    # CHAMBER CRITICAL TEMPERATURE
    # ========================================================
    #
    # We deliberately DO NOT stop cooling merely because the
    # chamber temperature is high.
    #
    # This condition will later trigger critical escalation
    # and rerouting.
    # ========================================================

    if (
        fault_type == FAULT_CHAMBER_CRITICAL
        and system_state == STATE_CRITICAL_FAILURE
    ):

        return {
            **default_result,
            "action_required": True,
            "reason": (
                "Critical chamber temperature requires "
                "escalation/rerouting. No automatic cooling "
                "shutdown command generated."
            ),
        }

    return default_result