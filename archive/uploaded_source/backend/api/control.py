"""
Cold-Chain Control Command API

Responsibilities:
1. Allow Simulator / ESP32-S3 to fetch pending commands.
2. Allow Simulator / ESP32-S3 to acknowledge commands.
3. Provide command history for dashboard/auditing.

Architecture:

    Self-Healing Engine
            ↓
    control_commands
            ↓
    GET pending command
            ↓
    Simulator / ESP32-S3
            ↓
    Apply actuator state
            ↓
    ACK command
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from backend.database.db import (
    get_pending_control_command,
    acknowledge_control_command,
    get_control_command_history,
)


router = APIRouter(
    prefix="/api/v1/control",
    tags=["Control"]
)


# ============================================================
# GET PENDING COMMAND
# ============================================================

@router.get("/{device_id}/pending")
def pending_command(device_id: str):

    command = get_pending_control_command(
        device_id
    )

    if command is None:

        return {
            "device_id": device_id,
            "command_available": False,
            "command": None
        }

    return {
        "device_id": device_id,

        "command_available": True,

        "command": {
            "id":
                command["id"],

            "session_id":
                command["session_id"],

            "command_type":
                command["command_type"],

            "primary_cooling":
                bool(
                    command["primary_cooling"]
                ),

            "backup_cooling":
                bool(
                    command["backup_cooling"]
                ),

            "reason":
                command["reason"],

            "triggered_by_fault":
                command["triggered_by_fault"],

            "status":
                command["status"],

            "created_at":
                command["created_at"]
        }
    }


# ============================================================
# ACKNOWLEDGE COMMAND
# ============================================================

@router.post("/{command_id}/acknowledge")
def acknowledge_command(command_id: int):

    acknowledged_at = datetime.now(
        timezone.utc
    ).isoformat()

    updated = acknowledge_control_command(
        command_id=command_id,
        acknowledged_at=acknowledged_at
    )

    if not updated:

        raise HTTPException(
            status_code=404,
            detail=(
                "Pending control command not found "
                "or command already acknowledged."
            )
        )

    return {
        "acknowledged": True,
        "command_id": command_id,
        "status": "ACKNOWLEDGED",
        "acknowledged_at": acknowledged_at
    }


# ============================================================
# COMMAND HISTORY
# ============================================================

@router.get("/{device_id}/history")
def command_history(
    device_id: str,
    limit: int = Query(
        default=100,
        ge=1,
        le=1000
    )
):

    commands = get_control_command_history(
        device_id=device_id,
        limit=limit
    )

    return {
        "device_id": device_id,
        "count": len(commands),
        "commands": commands
    }